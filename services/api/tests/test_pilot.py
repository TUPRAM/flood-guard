from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from floodguard_api.app import create_app
from floodguard_api.config import RepositoryPaths
from floodguard_api.dataset_registry import (
    FIXTURE_STUDY_AREA,
    MAE_SAI_STUDY_AREA,
    DatasetRegistry,
)
from floodguard_api.models import DatasetMode, OperationalStatus, StatusResponse
from floodguard_api.pilot import (
    NO_ACCEPTANCE_RECEIPT_BYTES,
    REQUIRED_ACCEPTANCE_CRITERIA,
    OperationalBoundaryError,
    PilotConfigurationError,
    PilotControl,
    PilotKeyring,
    audit_retention_binding_sha256,
    issue_test_credential,
    provision_audit_ledger,
)
from floodguard_api.pilot_models import (
    AcceptanceReceiptRequest,
    PilotCredential,
    PilotRole,
    RetentionRequest,
    SignedAcceptanceReceipt,
)
from floodguard_api.repository import ArtifactRepository

NOW = datetime(2026, 7, 16, 10, 0, tzinfo=UTC)
KEY_ID = "pilot-test-key"
KEY = b"floodguard-pilot-test-key-material-0001"
OFFICIAL_SOURCE_TIMESTAMP = "2026-07-12T09:00:00Z"
OFFICIAL_PAYLOAD = {
    "dataset_mode": "official_input",
    "operational_status": "agency_operational",
    "study_area": "example_study_area",
    "data_version": "example-official-v1",
    "source_timestamp": OFFICIAL_SOURCE_TIMESTAMP,
}
OFFICIAL_RESPONSE_SHA256 = hashlib.sha256(
    json.dumps(OFFICIAL_PAYLOAD, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()
ARTIFACT_MANIFEST_PAYLOAD = {
    "schema_version": "1.0",
    "manifest_type": "floodguard.served-responses.v1",
    "manifest_id": "example-official-v1",
    "dataset_mode": "official_input",
    "study_area": "example_study_area",
    "data_version": "example-official-v1",
    "source_timestamp": OFFICIAL_SOURCE_TIMESTAMP,
    "served_responses": [
        {
            "response_id": "status-response-v1",
            "response_sha256": OFFICIAL_RESPONSE_SHA256,
            "source_timestamp": OFFICIAL_SOURCE_TIMESTAMP,
            "data_version": "example-official-v1",
            "artifacts": [{"artifact_id": "area-decisions-v1", "sha256": "9" * 64}],
        }
    ],
}
ARTIFACT_MANIFEST_BYTES = json.dumps(
    ARTIFACT_MANIFEST_PAYLOAD,
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")
FIELD_VALIDATION_PAYLOAD = {
    "schema_version": "1.0",
    "protocol_version": "field-validation-v1",
    "receipt_id": "test-field-validation-v1",
    "dataset_mode": "official_input",
    "operational_status": "planning_only",
    "source_timestamp": "2026-07-12T09:00:00Z",
    "generated_at": "2026-07-15T10:00:00Z",
    "confidence_class": "high",
    "source_name": "test-only synthetic pilot evidence",
    "assumptions": ["Synthetic API contract test; not real Mae Sai evidence."],
    "official_warning": False,
    "data_version": "example-official-v1",
    "git_commit": "abcdef1",
    "can_feed_decision_layer": False,
    "study_area": "example_study_area",
    "event_id": "test-event-2026",
    "observation_window": {
        "start": "2026-07-10T01:00:00Z",
        "end": "2026-07-12T09:00:00Z",
    },
    "evidence_hashes": {
        "product_manifest_sha256": "1" * 64,
        "model_manifest_sha256": "2" * 64,
        "probability_raster_sha256": "3" * 64,
        "zonal_receipt_sha256": "4" * 64,
        "reporting_geometry_sha256": "5" * 64,
        "sampling_plan_sha256": "6" * 64,
        "holdout_geometry_sha256": "7" * 64,
    },
    "stratum_counts": [{"stratum_id": "test-stratum", "observed": 2, "usable": 2, "excluded": 0}],
    "reviewer_calibration": {
        "status": "passed",
        "metric": "test_agreement",
        "score": 0.9,
        "threshold": 0.8,
        "evidence_sha256": "8" * 64,
    },
    "metrics": {
        "iou": 0.5,
        "f1_dice": 0.6,
        "precision": 0.7,
        "recall": 0.8,
        "signed_area_error_ratio": -0.1,
        "absolute_area_error_ratio": 0.1,
        "brier_score": 0.2,
        "expected_calibration_error": 0.1,
    },
    "error_categories": [],
    "safety_incidents": 0,
    "stop_work_events": 0,
    "data_protection_confirmed": True,
    "licensing_confirmed": True,
    "decision_th": "หลักฐานสังเคราะห์สำหรับการทดสอบสัญญาเท่านั้น",
    "decision_en": "Synthetic contract-test evidence only.",
    "issued_at": "2026-07-15T10:00:00Z",
    "review_due_at": "2026-08-14T10:00:00Z",
    "accountable_role_ids": ["test-data-owner", "test-validation-reviewer"],
    "status": "accepted",
}
FIELD_VALIDATION_BYTES = json.dumps(
    FIELD_VALIDATION_PAYLOAD,
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")
ARTIFACT_MANIFEST_SHA256 = hashlib.sha256(ARTIFACT_MANIFEST_BYTES).hexdigest()
FIELD_VALIDATION_SHA256 = hashlib.sha256(FIELD_VALIDATION_BYTES).hexdigest()


def _control(
    tmp_path: Path,
    *,
    artifact_root: Path | None = None,
    retention_artifacts: list[dict[str, object]] | None = None,
) -> PilotControl:
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)
    keyring = PilotKeyring({KEY_ID: KEY}, active_key_id=KEY_ID)
    governed_root = artifact_root or tmp_path / "artifacts"
    governed_root.mkdir(parents=True, exist_ok=True)
    quarantine = governed_root / ".retention-quarantine"
    quarantine.mkdir(exist_ok=True)
    quarantine.chmod(0o700)
    artifact_manifest = governed_root / "source-manifests" / "artifact-manifest.json"
    field_receipt = governed_root / "source-manifests" / "field-validation-receipt.json"
    acceptance_receipt = governed_root / "acceptance" / "pilot-acceptance-receipt.json"
    audit_log = governed_root / "audit" / "ledger" / "pilot.jsonl"
    audit_anchor = governed_root / "audit" / "anchor" / "pilot.anchor.json"
    artifact_manifest.parent.mkdir(parents=True, exist_ok=True)
    acceptance_receipt.parent.mkdir(parents=True, exist_ok=True)
    artifact_manifest.write_bytes(ARTIFACT_MANIFEST_BYTES)
    field_receipt.write_bytes(FIELD_VALIDATION_BYTES)
    acceptance_receipt.write_bytes(NO_ACCEPTANCE_RECEIPT_BYTES)
    provision_audit_ledger(
        ledger_path=audit_log,
        anchor_path=audit_anchor,
        keyring=keyring,
    )
    audit_instance_id = json.loads(audit_anchor.read_text(encoding="utf-8"))["audit_instance_id"]
    governed_evidence = {
        "pilot-acceptance-receipt": (
            "acceptance/pilot-acceptance-receipt.json",
            "acceptance_receipt",
            NO_ACCEPTANCE_RECEIPT_BYTES,
            hashlib.sha256(NO_ACCEPTANCE_RECEIPT_BYTES).hexdigest(),
        ),
        "pilot-audit-ledger": (
            "audit/ledger/pilot.jsonl",
            "audit_log",
            audit_log.read_bytes(),
            audit_retention_binding_sha256(audit_instance_id, "pilot-audit-ledger"),
        ),
        "pilot-audit-anchor": (
            "audit/anchor/pilot.anchor.json",
            "audit_log",
            audit_anchor.read_bytes(),
            audit_retention_binding_sha256(audit_instance_id, "pilot-audit-anchor"),
        ),
        "current-served-artifact-manifest": (
            "source-manifests/artifact-manifest.json",
            "source_manifest",
            ARTIFACT_MANIFEST_BYTES,
            hashlib.sha256(ARTIFACT_MANIFEST_BYTES).hexdigest(),
        ),
        "current-field-validation-receipt": (
            "source-manifests/field-validation-receipt.json",
            "source_manifest",
            FIELD_VALIDATION_BYTES,
            hashlib.sha256(FIELD_VALIDATION_BYTES).hexdigest(),
        ),
    }
    mandatory_retention_artifacts: list[dict[str, object]] = []
    for artifact_id, (
        relative_path,
        category,
        content,
        evidence_binding_sha256,
    ) in governed_evidence.items():
        governed_path = governed_root.joinpath(*relative_path.split("/"))
        assert governed_path.read_bytes() == content
        mandatory_retention_artifacts.append(
            {
                "artifact_id": artifact_id,
                "relative_path": relative_path,
                "category": category,
                "created_at": NOW.isoformat().replace("+00:00", "Z"),
                "legal_hold": True,
                "sha256": hashlib.sha256(content).hexdigest(),
                "evidence_binding_sha256": evidence_binding_sha256,
            }
        )
    extra_retention_artifacts = []
    for artifact in retention_artifacts or []:
        normalized = dict(artifact)
        normalized.setdefault("evidence_binding_sha256", normalized["sha256"])
        extra_retention_artifacts.append(normalized)
    catalog_payload = {
        "schema_version": "1.0",
        "catalog_id": "test-retention-catalog-v1",
        "generated_at": NOW.isoformat().replace("+00:00", "Z"),
        "review_due_at": (NOW + timedelta(days=30)).isoformat().replace("+00:00", "Z"),
        "artifacts": mandatory_retention_artifacts + extra_retention_artifacts,
    }
    catalog_payload_bytes = json.dumps(
        catalog_payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    payload_sha256 = hashlib.sha256(catalog_payload_bytes).hexdigest()
    catalog_key_id, catalog_signature = keyring.active_sign(catalog_payload_bytes)
    retention_catalog = evidence_root / "retention-catalog.json"
    retention_catalog.write_bytes(
        json.dumps(
            {
                "payload": catalog_payload,
                "signature": {
                    "algorithm": "HMAC-SHA256",
                    "key_id": catalog_key_id,
                    "payload_sha256": payload_sha256,
                    "value": catalog_signature,
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    return PilotControl(
        keyring=keyring,
        audit_log_path=audit_log,
        audit_anchor_path=audit_anchor,
        artifact_root=governed_root,
        retention_catalog_path=retention_catalog,
        current_artifact_manifest_path=artifact_manifest,
        current_field_validation_receipt_path=field_receipt,
        clock=lambda: NOW,
    )


def _token(
    control: PilotControl,
    role: PilotRole,
    *,
    expires_at: datetime | None = None,
) -> str:
    credential = PilotCredential(
        subject=f"tester-{role.value}",
        roles=[role],
        issued_at=NOW - timedelta(minutes=1),
        expires_at=expires_at or NOW + timedelta(minutes=59),
        token_id=f"token-{role.value}",
        key_id=KEY_ID,
    )
    return issue_test_credential(control.keyring, credential)


def _headers(control: PilotControl, role: PilotRole) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(control, role)}"}


def _resign_retention_catalog(
    control: PilotControl,
    payload: dict[str, object],
) -> None:
    payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()
    key_id, signature = control.keyring.active_sign(payload_bytes)
    assert control.retention.catalog_path is not None
    control.retention.catalog_path.write_bytes(
        json.dumps(
            {
                "payload": payload,
                "signature": {
                    "algorithm": "HMAC-SHA256",
                    "key_id": key_id,
                    "payload_sha256": payload_sha256,
                    "value": signature,
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )


def _install_receipt(
    control: PilotControl,
    receipt: SignedAcceptanceReceipt | dict[str, object],
) -> SignedAcceptanceReceipt:
    installed = SignedAcceptanceReceipt.model_validate(receipt)
    receipt_bytes = json.dumps(
        installed.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert control.retention.catalog_path is not None
    assert control.retention.root is not None
    signed_catalog = json.loads(control.retention.catalog_path.read_text(encoding="utf-8"))
    entry = next(
        item
        for item in signed_catalog["payload"]["artifacts"]
        if item["artifact_id"] == "pilot-acceptance-receipt"
    )
    receipt_path = control.retention.root.joinpath(*entry["relative_path"].split("/"))
    receipt_path.write_bytes(receipt_bytes)
    digest = hashlib.sha256(receipt_bytes).hexdigest()
    entry["sha256"] = digest
    entry["evidence_binding_sha256"] = digest
    _resign_retention_catalog(control, signed_catalog["payload"])
    control.installed_receipt = installed
    control.installed_receipt_path = receipt_path
    return installed


def _bind_served_payload(control: PilotControl, payload: object) -> str:
    value = payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload
    assert isinstance(value, dict)
    response_bytes = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    manifest = json.loads(json.dumps(ARTIFACT_MANIFEST_PAYLOAD))
    manifest["study_area"] = value["study_area"]
    manifest["data_version"] = value["data_version"]
    manifest["source_timestamp"] = value["source_timestamp"]
    lineage = manifest["served_responses"][0]
    lineage["response_sha256"] = hashlib.sha256(response_bytes).hexdigest()
    lineage["data_version"] = value["data_version"]
    lineage["source_timestamp"] = value["source_timestamp"]
    manifest_bytes = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert control.current_artifact_manifest_path is not None
    control.current_artifact_manifest_path.write_bytes(manifest_bytes)
    assert control.retention.catalog_path is not None
    signed_catalog = json.loads(control.retention.catalog_path.read_text(encoding="utf-8"))
    entry = next(
        item
        for item in signed_catalog["payload"]["artifacts"]
        if item["artifact_id"] == "current-served-artifact-manifest"
    )
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    entry["sha256"] = digest
    entry["evidence_binding_sha256"] = digest
    _resign_retention_catalog(control, signed_catalog["payload"])
    return digest


def _use_official_input(repository: ArtifactRepository) -> None:
    official_status = repository.status().model_copy(
        update={
            "dataset_mode": DatasetMode.OFFICIAL_INPUT,
            "operational_status": OperationalStatus.PLANNING_ONLY,
            "official_warning": False,
            "data_version": "example-official-v1",
        }
    )
    repository.status = (  # type: ignore[method-assign]
        lambda study_area=FIXTURE_STUDY_AREA: official_status
    )


def _acceptance_request(dataset_mode: str = "official_input") -> dict[str, object]:
    return {
        "acceptance_id": "test-acceptance-v1",
        "study_area": "example_study_area",
        "dataset_mode": dataset_mode,
        "data_version": "example-official-v1",
        "artifact_manifest_sha256": ARTIFACT_MANIFEST_SHA256,
        "source_timestamp": OFFICIAL_SOURCE_TIMESTAMP,
        "acceptance_criteria_ids": sorted(REQUIRED_ACCEPTANCE_CRITERIA),
        "field_validation_receipt_sha256": FIELD_VALIDATION_SHA256,
        "field_validation_protocol_version": "field-validation-v1",
        "expires_at": "2026-08-15T10:00:00Z",
    }


def test_public_pilot_readiness_is_non_operational_without_secrets(client: TestClient) -> None:
    response = client.get("/api/v1/pilot/readiness")
    assert response.status_code == 200
    payload = response.json()
    assert payload["operational_status"] == "non_operational"
    assert payload["agency_operational_allowed"] is False
    assert payload["acceptance_receipt_state"] == "missing"
    assert payload["deployment_state"] == "pilot_not_configured"
    assert {role.value for role in PilotRole} == set(payload["roles"])
    assert "secret" not in json.dumps(payload).lower()


@pytest.mark.parametrize("credential", [None, "Bearer invalid", "Basic abc"])
def test_missing_and_invalid_credentials_are_rejected(
    tmp_path: Path,
    credential: str | None,
) -> None:
    control = _control(tmp_path)
    headers = {"Authorization": credential} if credential else {}
    with TestClient(create_app(pilot_control=control)) as client:
        response = client.get("/api/v1/pilot/session", headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"] == "invalid_pilot_credential"


def test_expired_and_tampered_credentials_are_rejected(tmp_path: Path) -> None:
    control = _control(tmp_path)
    expired = _token(
        control,
        PilotRole.PILOT_ADMIN,
        expires_at=NOW - timedelta(seconds=1),
    )
    valid = _token(control, PilotRole.PILOT_ADMIN)
    tampered = valid[:-1] + ("0" if valid[-1] != "0" else "1")
    with TestClient(create_app(pilot_control=control)) as client:
        expired_response = client.get(
            "/api/v1/pilot/session",
            headers={"Authorization": f"Bearer {expired}"},
        )
        tampered_response = client.get(
            "/api/v1/pilot/session",
            headers={"Authorization": f"Bearer {tampered}"},
        )
    assert expired_response.status_code == 401
    assert tampered_response.status_code == 401


def test_overlong_credential_and_acceptance_lifetimes_are_rejected(tmp_path: Path) -> None:
    control = _control(tmp_path)
    overlong_credential = PilotCredential.model_construct(
        schema_version="1.0",
        subject="tester-pilot_admin",
        roles=[PilotRole.PILOT_ADMIN],
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=2),
        token_id="token-overlong-admin",
        key_id=KEY_ID,
    )
    overlong_token = issue_test_credential(control.keyring, overlong_credential)
    overlong_receipt = _acceptance_request()
    overlong_receipt["expires_at"] = "2026-08-16T10:00:00Z"

    with TestClient(create_app(pilot_control=control)) as client:
        credential_response = client.get(
            "/api/v1/pilot/session",
            headers={"Authorization": f"Bearer {overlong_token}"},
        )
        receipt_response = client.post(
            "/api/v1/pilot/acceptance-receipts",
            headers=_headers(control, PilotRole.PILOT_ADMIN),
            json=overlong_receipt,
        )

    assert credential_response.status_code == 401
    assert receipt_response.status_code == 422


@pytest.mark.parametrize(
    ("role", "monitoring_status", "audit_status"),
    [
        (PilotRole.PUBLIC_VIEWER, 403, 403),
        (PilotRole.COMMAND_VIEWER, 200, 403),
        (PilotRole.ANALYST, 200, 403),
        (PilotRole.DATA_STEWARD, 200, 403),
        (PilotRole.PILOT_ADMIN, 200, 200),
    ],
)
def test_server_enforces_role_matrix_on_every_endpoint(
    tmp_path: Path,
    role: PilotRole,
    monitoring_status: int,
    audit_status: int,
) -> None:
    control = _control(tmp_path)
    headers = _headers(control, role)
    with TestClient(create_app(pilot_control=control)) as client:
        assert client.get("/api/v1/pilot/session", headers=headers).status_code == 200
        assert (
            client.get("/api/v1/pilot/monitoring", headers=headers).status_code == monitoring_status
        )
        assert client.get("/api/v1/pilot/audit-log", headers=headers).status_code == audit_status


def test_fixture_data_and_offline_readiness_remain_anonymous(
    tmp_path: Path,
    repository: ArtifactRepository,
) -> None:
    control = _control(tmp_path)
    with TestClient(create_app(repository, pilot_control=control)) as client:
        for route in (
            "/api/v1/status",
            "/api/v1/study-areas",
            "/api/v1/areas",
            "/api/v1/layers",
            "/api/v1/scenarios",
            "/api/v1/model-runs",
            "/api/v1/model-registry",
            "/api/v1/model-registry/fixture-sar-accepted-candidate-v1",
            "/api/v1/model-registry/fixture-sar-accepted-candidate-v1/evidence",
            "/api/v1/model-evaluations",
            "/api/v1/observation-products",
            "/api/v1/data-readiness",
            "/api/v1/pilot/readiness",
        ):
            assert client.get(route).status_code == 200, route

    assert control.audit.read().entry_count == 0


def test_model_authorization_uses_the_requested_study_area_in_a_mixed_registry(
    tmp_path: Path,
) -> None:
    class MixedModeRegistry(DatasetRegistry):
        def status(
            self,
            study_area: str = FIXTURE_STUDY_AREA,
        ) -> StatusResponse:
            current = super().status(study_area)
            if study_area == MAE_SAI_STUDY_AREA:
                return current.model_copy(
                    update={
                        "dataset_mode": DatasetMode.OFFICIAL_INPUT,
                        "operational_status": OperationalStatus.PLANNING_ONLY,
                    }
                )
            return current

    repository = MixedModeRegistry()
    control = _control(tmp_path)
    official_routes = (
        "/api/v1/model-runs",
        "/api/v1/model-runs/mae-sai-geoai-evaluation-blocked-v2",
        "/api/v1/model-registry",
        "/api/v1/model-registry/mae-sai-model-evaluation-blocked-v1",
        "/api/v1/model-registry/mae-sai-model-evaluation-blocked-v1/evidence",
        "/api/v1/model-evaluations",
        "/api/v1/observation-products",
    )

    with TestClient(create_app(repository, pilot_control=control)) as client:
        # The default fixture remains intentionally anonymous.
        assert client.get("/api/v1/model-runs").status_code == 200
        assert client.get("/api/v1/model-registry").status_code == 200

        for route in official_routes:
            response = client.get(
                route,
                params={"study_area": MAE_SAI_STUDY_AREA},
            )
            assert response.status_code == 401, route
            assert response.json()["error"] == "invalid_pilot_credential"

    entries = control.audit.read().entries
    assert len(entries) == len(official_routes)
    assert all(entry.action == "api:model-evidence:read" for entry in entries)
    assert all(entry.outcome == "denied" for entry in entries)
    assert all(
        entry.details
        == {
            "capability": "assessment:run",
            "dataset_mode": "official_input",
            "reason": "invalid_pilot_credential",
        }
        for entry in entries
    )


@pytest.mark.parametrize(
    ("route", "capability", "action"),
    [
        ("/api/v1/areas", "monitoring:read", "api:command-data:read"),
        ("/api/v1/layers", "monitoring:read", "api:command-data:read"),
        ("/api/v1/scenarios", "assessment:run", "api:scenario:operate"),
        ("/api/v1/model-runs", "assessment:run", "api:model-evidence:read"),
        ("/api/v1/model-registry", "assessment:run", "api:model-evidence:read"),
        ("/api/v1/model-evaluations", "assessment:run", "api:model-evidence:read"),
        ("/api/v1/observation-products", "assessment:run", "api:model-evidence:read"),
        ("/api/v1/data-readiness", "assessment:run", "api:data-readiness:read"),
        ("/api/v1/pilot/readiness", "monitoring:read", "api:pilot-readiness:read"),
    ],
)
def test_anonymous_official_input_data_operations_are_rejected_and_audited(
    tmp_path: Path,
    repository: ArtifactRepository,
    route: str,
    capability: str,
    action: str,
) -> None:
    _use_official_input(repository)
    control = _control(tmp_path)
    with TestClient(create_app(repository, pilot_control=control)) as client:
        response = client.get(route)

    assert response.status_code == 401
    assert response.json()["error"] == "invalid_pilot_credential"
    record = control.audit.read().entries[-1]
    assert record.actor_subject == "anonymous-request"
    assert record.actor_roles == []
    assert record.action == action
    assert record.outcome == "denied"
    assert record.details == {
        "capability": capability,
        "dataset_mode": "official_input",
        "reason": "invalid_pilot_credential",
    }


@pytest.mark.parametrize(
    ("role", "command_status", "studio_status"),
    [
        (PilotRole.PUBLIC_VIEWER, 403, 403),
        (PilotRole.COMMAND_VIEWER, 200, 403),
        (PilotRole.ANALYST, 200, 200),
        (PilotRole.DATA_STEWARD, 200, 200),
        (PilotRole.PILOT_ADMIN, 200, 200),
    ],
)
def test_official_input_data_operations_enforce_role_capabilities(
    tmp_path: Path,
    repository: ArtifactRepository,
    role: PilotRole,
    command_status: int,
    studio_status: int,
) -> None:
    _use_official_input(repository)
    control = _control(tmp_path)
    headers = _headers(control, role)
    with TestClient(create_app(repository, pilot_control=control)) as client:
        assert client.get("/api/v1/areas", headers=headers).status_code == command_status
        assert client.get("/api/v1/model-runs", headers=headers).status_code == studio_status
        assert client.get("/api/v1/model-registry", headers=headers).status_code == studio_status
        assert client.get("/api/v1/model-evaluations", headers=headers).status_code == studio_status
        assert (
            client.get("/api/v1/observation-products", headers=headers).status_code
            == studio_status
        )
        assert client.get("/api/v1/data-readiness", headers=headers).status_code == studio_status


def test_protected_operation_audit_records_are_redacted_and_action_specific(
    tmp_path: Path,
    repository: ArtifactRepository,
) -> None:
    _use_official_input(repository)
    control = _control(tmp_path)
    command_headers = _headers(control, PilotRole.COMMAND_VIEWER)
    analyst_headers = _headers(control, PilotRole.ANALYST)
    public_headers = _headers(control, PilotRole.PUBLIC_VIEWER)
    admin_headers = _headers(control, PilotRole.PILOT_ADMIN)
    command_token = command_headers["Authorization"]

    with TestClient(create_app(repository, pilot_control=control)) as client:
        assert client.get("/api/v1/pilot/session", headers=command_headers).status_code == 200
        assert client.get("/api/v1/pilot/monitoring", headers=command_headers).status_code == 200
        assert client.get("/api/v1/areas", headers=public_headers).status_code == 403
        assert client.get("/api/v1/areas", headers=command_headers).status_code == 200
        assert client.get("/api/v1/model-runs", headers=command_headers).status_code == 403
        assert client.get("/api/v1/model-runs", headers=analyst_headers).status_code == 200
        assessment = client.post(
            "/api/v1/pilot/operational-assessments",
            headers=analyst_headers,
            json={
                "dataset_mode": "official_input",
                "study_area": "fixture_thailand_demo",
                "data_version": "example-official-v1",
                "expected_artifact_manifest_sha256": ARTIFACT_MANIFEST_SHA256,
                "expected_field_validation_receipt_sha256": FIELD_VALIDATION_SHA256,
                "receipt": None,
            },
        )
        assert assessment.status_code == 200
        assert client.get("/api/v1/pilot/audit-log", headers=admin_headers).status_code == 200

    entries = control.audit.read().entries
    outcomes = {(entry.action, entry.outcome) for entry in entries}
    assert ("api:pilot-session:read", "allowed") in outcomes
    assert ("api:pilot-monitoring:read", "allowed") in outcomes
    assert ("api:command-data:read", "denied") in outcomes
    assert ("api:command-data:read", "allowed") in outcomes
    assert ("api:model-evidence:read", "denied") in outcomes
    assert ("api:model-evidence:read", "allowed") in outcomes
    assert ("api:operational-assessment:run", "allowed") in outcomes
    assert ("api:audit-log:read", "allowed") in outcomes
    for entry in entries:
        assert set(entry.details).issubset({"capability", "dataset_mode", "reason"})

    raw_audit = control.audit.path.read_text(encoding="utf-8")  # type: ignore[union-attr]
    assert command_token not in raw_audit
    assert "Authorization" not in raw_audit
    assert "C:\\\\Users\\\\" not in raw_audit
    assert KEY.decode() not in raw_audit


def test_signed_acceptance_receipt_rejects_payload_and_key_substitution(tmp_path: Path) -> None:
    control = _control(tmp_path)
    with TestClient(create_app(pilot_control=control)) as client:
        signed = client.post(
            "/api/v1/pilot/acceptance-receipts",
            headers=_headers(control, PilotRole.PILOT_ADMIN),
            json=_acceptance_request(),
        )
        assert signed.status_code == 201
        receipt = signed.json()

        verified = client.post(
            "/api/v1/pilot/acceptance-receipts/verify",
            headers=_headers(control, PilotRole.ANALYST),
            json=receipt,
        )
        assert verified.status_code == 200
        assert verified.json()["valid"] is True

        substituted = json.loads(json.dumps(receipt))
        substituted["payload"]["data_version"] = "substituted-version"
        rejected = client.post(
            "/api/v1/pilot/acceptance-receipts/verify",
            headers=_headers(control, PilotRole.ANALYST),
            json=substituted,
        )
        assert rejected.status_code == 200
        assert rejected.json()["valid"] is False

        wrong_key = json.loads(json.dumps(receipt))
        wrong_key["signature"]["key_id"] = "unknown-pilot-key"
        rejected_key = client.post(
            "/api/v1/pilot/acceptance-receipts/verify",
            headers=_headers(control, PilotRole.ANALYST),
            json=wrong_key,
        )
        assert rejected_key.json()["valid"] is False


def test_fixture_cannot_receive_or_use_agency_acceptance(tmp_path: Path) -> None:
    control = _control(tmp_path)
    headers = _headers(control, PilotRole.PILOT_ADMIN)
    with TestClient(create_app(pilot_control=control)) as client:
        fixture_signing = client.post(
            "/api/v1/pilot/acceptance-receipts",
            headers=headers,
            json=_acceptance_request("fixture_demo"),
        )
        assert fixture_signing.status_code == 422

        official_receipt = client.post(
            "/api/v1/pilot/acceptance-receipts",
            headers=headers,
            json=_acceptance_request(),
        ).json()
        assessment = client.post(
            "/api/v1/pilot/operational-assessments",
            headers=headers,
            json={
                "dataset_mode": "fixture_demo",
                "study_area": "fixture_thailand_demo",
                "data_version": "fixture-2026-06-29-v1",
                "expected_artifact_manifest_sha256": ARTIFACT_MANIFEST_SHA256,
                "expected_field_validation_receipt_sha256": FIELD_VALIDATION_SHA256,
                "receipt": official_receipt,
            },
        )
    assert assessment.status_code == 200
    assert assessment.json() == {
        "operational_status": "non_operational",
        "acceptance_receipt_valid": False,
        "reason": "Fixture and candidate datasets are always non-operational.",
    }


def test_operational_assessment_binds_both_current_evidence_digests(tmp_path: Path) -> None:
    control = _control(tmp_path)
    headers = _headers(control, PilotRole.PILOT_ADMIN)
    with TestClient(create_app(pilot_control=control)) as client:
        receipt = client.post(
            "/api/v1/pilot/acceptance-receipts",
            headers=headers,
            json=_acceptance_request(),
        ).json()
        _install_receipt(control, receipt)
        request = {
            "dataset_mode": "official_input",
            "study_area": "example_study_area",
            "data_version": "example-official-v1",
            "expected_artifact_manifest_sha256": ARTIFACT_MANIFEST_SHA256,
            "expected_field_validation_receipt_sha256": FIELD_VALIDATION_SHA256,
            "receipt": receipt,
        }
        accepted = client.post(
            "/api/v1/pilot/operational-assessments",
            headers=headers,
            json=request,
        )
        assert accepted.json()["operational_status"] == "agency_operational"

        artifact_substitution = {**request, "expected_artifact_manifest_sha256": "3" * 64}
        artifact_rejected = client.post(
            "/api/v1/pilot/operational-assessments",
            headers=headers,
            json=artifact_substitution,
        )
        assert artifact_rejected.json()["operational_status"] == "planning_only"

        field_substitution = {
            **request,
            "expected_field_validation_receipt_sha256": "4" * 64,
        }
        field_rejected = client.post(
            "/api/v1/pilot/operational-assessments",
            headers=headers,
            json=field_substitution,
        )
        assert field_rejected.json()["operational_status"] == "planning_only"


def test_acceptance_signing_rejects_evidence_scope_and_byte_substitution(tmp_path: Path) -> None:
    control = _control(tmp_path)
    headers = _headers(control, PilotRole.PILOT_ADMIN)
    with TestClient(create_app(pilot_control=control)) as client:
        wrong_scope = _acceptance_request()
        wrong_scope["study_area"] = "different_study_area"
        scope_response = client.post(
            "/api/v1/pilot/acceptance-receipts",
            headers=headers,
            json=wrong_scope,
        )
        assert scope_response.status_code == 422

        assert control.current_field_validation_receipt_path is not None
        substituted = dict(FIELD_VALIDATION_PAYLOAD)
        substituted["decision_en"] = "Substituted after evidence digest registration."
        control.current_field_validation_receipt_path.write_bytes(
            json.dumps(substituted, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        byte_response = client.post(
            "/api/v1/pilot/acceptance-receipts",
            headers=headers,
            json=_acceptance_request(),
        )
        assert byte_response.status_code == 503

    expired_control = _control(tmp_path / "expired-field-receipt")
    assert expired_control.current_field_validation_receipt_path is not None
    expired_field = json.loads(json.dumps(FIELD_VALIDATION_PAYLOAD))
    expired_field["review_due_at"] = "2026-07-16T10:00:00Z"
    expired_bytes = json.dumps(
        expired_field,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    expired_control.current_field_validation_receipt_path.write_bytes(expired_bytes)
    expired_request = _acceptance_request()
    expired_request["field_validation_receipt_sha256"] = hashlib.sha256(expired_bytes).hexdigest()
    with TestClient(create_app(pilot_control=expired_control)) as client:
        expired_response = client.post(
            "/api/v1/pilot/acceptance-receipts",
            headers=_headers(expired_control, PilotRole.PILOT_ADMIN),
            json=expired_request,
        )
    assert expired_response.status_code == 503

    duplicate_control = _control(tmp_path / "duplicate-key-manifest")
    assert duplicate_control.current_artifact_manifest_path is not None
    duplicate_manifest = (
        b'{"artifact_manifest":"example-official-v1",'
        b'"data_version":"example-official-v1",'
        b'"study_area":"different_study_area",'
        b'"study_area":"example_study_area"}\n'
    )
    duplicate_control.current_artifact_manifest_path.write_bytes(duplicate_manifest)
    duplicate_request = _acceptance_request()
    duplicate_request["artifact_manifest_sha256"] = hashlib.sha256(duplicate_manifest).hexdigest()
    with TestClient(create_app(pilot_control=duplicate_control)) as client:
        duplicate_response = client.post(
            "/api/v1/pilot/acceptance-receipts",
            headers=_headers(duplicate_control, PilotRole.PILOT_ADMIN),
            json=duplicate_request,
        )
    assert duplicate_response.status_code == 503


def test_acceptance_signing_requires_exact_bootstrap_sentinel_target_bytes(
    tmp_path: Path,
) -> None:
    control = _control(tmp_path)
    identity = control.authenticate(f"Bearer {_token(control, PilotRole.PILOT_ADMIN)}")
    assert control.retention.root is not None
    acceptance_target = control.retention.root / "acceptance" / "pilot-acceptance-receipt.json"
    acceptance_target.write_bytes(b'{"state":"not-installed","substituted":true}\n')

    with pytest.raises(PilotConfigurationError, match="governed retention"):
        control.sign_acceptance(
            AcceptanceReceiptRequest.model_validate(_acceptance_request()),
            identity,
        )


@pytest.mark.parametrize(
    "evidence_attribute",
    ["current_artifact_manifest_path", "current_field_validation_receipt_path"],
)
def test_acceptance_signing_rejects_coordinated_evidence_swap_after_descriptor_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    evidence_attribute: str,
) -> None:
    control = _control(tmp_path)
    identity = control.authenticate(f"Bearer {_token(control, PilotRole.PILOT_ADMIN)}")
    target = getattr(control, evidence_attribute)
    assert isinstance(target, Path)
    original_bytes = target.read_bytes()
    saved = target.with_name(f"{target.name}.catalogued")
    substitute = target.with_name(f"{target.name}.substitute")
    substitute.write_bytes(b'{"substituted":"during-control-evidence-capture"}\n')
    real_open = Path.open
    state = {"attacked": False, "swapped": False}

    class SwapAfterDescriptorClose:
        def __init__(self, stream: object) -> None:
            self.stream = stream

        def __enter__(self) -> object:
            return self.stream.__enter__()  # type: ignore[attr-defined,no-any-return]

        def __exit__(self, *args: object) -> object:
            result = self.stream.__exit__(*args)  # type: ignore[attr-defined]
            target.replace(saved)
            substitute.replace(target)
            state["swapped"] = True
            return result

    def coordinated_open(path: Path, *args: object, **kwargs: object) -> object:
        stream = real_open(path, *args, **kwargs)
        mode = args[0] if args else kwargs.get("mode", "r")
        if not state["attacked"] and path == target and mode == "rb":
            state["attacked"] = True
            return SwapAfterDescriptorClose(stream)
        return stream

    monkeypatch.setattr(Path, "open", coordinated_open)
    try:
        with pytest.raises(PilotConfigurationError, match="governed retention"):
            control.sign_acceptance(
                AcceptanceReceiptRequest.model_validate(_acceptance_request()),
                identity,
            )
    finally:
        if state["swapped"]:
            target.unlink()
            saved.replace(target)

    assert state == {"attacked": True, "swapped": True}
    assert target.read_bytes() == original_bytes


def test_response_promotion_requires_configured_current_evidence_digests(tmp_path: Path) -> None:
    signing_control = _control(tmp_path / "signing")
    identity = signing_control.authenticate(
        f"Bearer {_token(signing_control, PilotRole.PILOT_ADMIN)}"
    )
    receipt = signing_control.sign_acceptance(
        AcceptanceReceiptRequest.model_validate(_acceptance_request()),
        identity,
    )
    official_payload = dict(OFFICIAL_PAYLOAD)

    missing_digests = PilotControl(
        keyring=signing_control.keyring,
        audit_log_path=tmp_path / "missing" / "audit.jsonl",
        artifact_root=tmp_path / "missing" / "artifacts",
        installed_receipt=receipt,
        clock=lambda: NOW,
    )
    with pytest.raises(
        OperationalBoundaryError,
        match="hashable current artifact and field-validation receipt files",
    ):
        missing_digests.assert_operational_boundary(official_payload)

    matching = _control(tmp_path / "matching")
    _install_receipt(matching, receipt)
    matching.assert_operational_boundary(official_payload)

    mismatched = _control(tmp_path / "mismatch")
    _install_receipt(mismatched, receipt)
    assert mismatched.current_artifact_manifest_path is not None
    mismatched.current_artifact_manifest_path.write_bytes(
        b'{"manifest_type":"floodguard.served-responses.v1",'
        b'"data_version":"example-official-v1","study_area":"example_study_area"}\n'
    )
    with pytest.raises(OperationalBoundaryError, match="hashable current artifact"):
        mismatched.assert_operational_boundary(official_payload)

    assert matching.current_artifact_manifest_path is not None
    matching.current_artifact_manifest_path.write_bytes(
        b'{"manifest_type":"floodguard.served-responses.v1",'
        b'"data_version":"example-official-v1","study_area":"example_study_area"}\n'
    )
    with pytest.raises(OperationalBoundaryError, match="hashable current artifact"):
        matching.assert_operational_boundary(official_payload)

    field_substitution = _control(tmp_path / "field-substitution")
    _install_receipt(field_substitution, receipt)
    assert field_substitution.current_field_validation_receipt_path is not None
    altered_field = dict(FIELD_VALIDATION_PAYLOAD)
    altered_field["decision_en"] = "Field receipt bytes were substituted."
    field_substitution.current_field_validation_receipt_path.write_bytes(
        json.dumps(altered_field, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    with pytest.raises(OperationalBoundaryError, match="governed retention"):
        field_substitution.assert_operational_boundary(official_payload)

    missing_audit = PilotControl(
        keyring=signing_control.keyring,
        audit_log_path=None,
        artifact_root=tmp_path / "missing-audit" / "artifacts",
        installed_receipt=receipt,
        current_artifact_manifest_path=signing_control.current_artifact_manifest_path,
        current_field_validation_receipt_path=(
            signing_control.current_field_validation_receipt_path
        ),
        clock=lambda: NOW,
    )
    with pytest.raises(OperationalBoundaryError, match="valid audit chain"):
        missing_audit.assert_operational_boundary(official_payload)
    assert (
        missing_audit.readiness(
            dataset_mode="official_input",
            study_area="example_study_area",
            data_version="example-official-v1",
        ).agency_operational_allowed
        is False
    )

    missing_retention = PilotControl(
        keyring=signing_control.keyring,
        audit_log_path=tmp_path / "missing-retention" / "audit.jsonl",
        artifact_root=None,
        installed_receipt=receipt,
        current_artifact_manifest_path=signing_control.current_artifact_manifest_path,
        current_field_validation_receipt_path=(
            signing_control.current_field_validation_receipt_path
        ),
        clock=lambda: NOW,
    )
    with pytest.raises(OperationalBoundaryError, match="governed retention"):
        missing_retention.assert_operational_boundary(official_payload)

    invalid_audit = _control(tmp_path / "invalid-audit")
    _install_receipt(invalid_audit, receipt)
    invalid_audit.audit.append(
        identity=identity,
        action="control:test",
        outcome="completed",
        details={"safe": "before"},
        now=NOW,
    )
    assert invalid_audit.audit.path is not None
    audit_text = invalid_audit.audit.path.read_text(encoding="utf-8")
    invalid_audit.audit.path.write_text(
        audit_text.replace("before", "after"),
        encoding="utf-8",
    )
    with pytest.raises(OperationalBoundaryError, match="valid audit chain"):
        invalid_audit.assert_operational_boundary(official_payload)


def test_current_evidence_rejects_symlink_substitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signing_control = _control(tmp_path / "signing")
    identity = signing_control.authenticate(
        f"Bearer {_token(signing_control, PilotRole.PILOT_ADMIN)}"
    )
    receipt = signing_control.sign_acceptance(
        AcceptanceReceiptRequest.model_validate(_acceptance_request()),
        identity,
    )
    control = _control(tmp_path / "symlink")
    _install_receipt(control, receipt)
    assert control.current_artifact_manifest_path is not None
    original = control.current_artifact_manifest_path
    target = original.with_name("alternate-manifest.json")
    target.write_bytes(ARTIFACT_MANIFEST_BYTES)
    original.unlink()
    try:
        original.symlink_to(target)
    except OSError:
        original.write_bytes(ARTIFACT_MANIFEST_BYTES)
        real_is_symlink = Path.is_symlink
        monkeypatch.setattr(
            Path,
            "is_symlink",
            lambda path: path == original or real_is_symlink(path),
        )

    with pytest.raises(
        OperationalBoundaryError,
        match="hashable current artifact and field-validation receipt files",
    ):
        control.assert_operational_boundary(
            {
                "dataset_mode": "official_input",
                "operational_status": "agency_operational",
                "study_area": "example_study_area",
                "data_version": "example-official-v1",
                "source_timestamp": OFFICIAL_SOURCE_TIMESTAMP,
            }
        )


def test_public_response_boundary_rejects_fixture_agency_status(
    tmp_path: Path,
    repository: ArtifactRepository,
) -> None:
    control = _control(tmp_path)
    fixture_status = repository.status().model_copy(
        update={"operational_status": OperationalStatus.AGENCY_OPERATIONAL}
    )
    repository.status = lambda: fixture_status  # type: ignore[method-assign]
    with TestClient(create_app(repository, pilot_control=control)) as client:
        response = client.get("/api/v1/status")
    assert response.status_code == 409
    assert response.json()["error"] == "agency_operational_boundary_rejected"


def test_audit_log_redacts_secrets_and_detects_chain_mutation(tmp_path: Path) -> None:
    control = _control(tmp_path)
    identity = control.authenticate(f"Bearer {_token(control, PilotRole.PILOT_ADMIN)}")
    control.audit.append(
        identity=identity,
        action="redaction:test",
        outcome="completed",
        details={
            "authorization": "Bearer should-not-appear",
            "workspace": r"C:\\Users\\operator\\secret",
            "safe": "manifest-v1",
        },
        now=NOW,
    )
    log = control.audit.read()
    assert log.chain_valid is True
    details = log.entries[0].details
    assert details["authorization"] == "[REDACTED]"
    assert details["workspace"] == "[REDACTED]"
    assert details["safe"] == "manifest-v1"

    assert control.audit.path is not None
    raw = control.audit.path.read_text(encoding="utf-8")
    control.audit.path.write_text(raw.replace("manifest-v1", "manifest-v2"), encoding="utf-8")
    assert control.audit.read().chain_valid is False
    assert control.audit.state() == "invalid"


def test_retention_dry_run_execute_and_policy_boundaries(tmp_path: Path) -> None:
    artifact_root = tmp_path / "external-artifacts"
    (artifact_root / "temporary").mkdir(parents=True)
    (artifact_root / "acceptance").mkdir()
    old_file = artifact_root / "temporary" / "old.tmp"
    new_file = artifact_root / "temporary" / "new.tmp"
    held_file = artifact_root / "temporary" / "held.tmp"
    receipt_file = artifact_root / "acceptance" / "acceptance.json"
    for path in (old_file, new_file, held_file, receipt_file):
        path.write_text(path.name, encoding="utf-8")

    retention_artifacts = [
        {
            "artifact_id": "old-temporary",
            "relative_path": "temporary/old.tmp",
            "category": "temporary",
            "created_at": "2026-07-01T00:00:00Z",
            "legal_hold": False,
            "sha256": hashlib.sha256(old_file.read_bytes()).hexdigest(),
        },
        {
            "artifact_id": "new-temporary",
            "relative_path": "temporary/new.tmp",
            "category": "temporary",
            "created_at": "2026-07-15T00:00:00Z",
            "legal_hold": False,
            "sha256": hashlib.sha256(new_file.read_bytes()).hexdigest(),
        },
        {
            "artifact_id": "held-temporary",
            "relative_path": "temporary/held.tmp",
            "category": "temporary",
            "created_at": "2026-06-01T00:00:00Z",
            "legal_hold": True,
            "sha256": hashlib.sha256(held_file.read_bytes()).hexdigest(),
        },
        {
            "artifact_id": "agency-acceptance",
            "relative_path": "acceptance/acceptance.json",
            "category": "acceptance_receipt",
            "created_at": "2020-01-01T00:00:00Z",
            "legal_hold": False,
            "sha256": hashlib.sha256(receipt_file.read_bytes()).hexdigest(),
        },
    ]
    control = _control(
        tmp_path,
        artifact_root=artifact_root,
        retention_artifacts=retention_artifacts,
    )
    request = {
        "mode": "dry_run",
        "artifact_ids": [
            "old-temporary",
            "new-temporary",
            "held-temporary",
            "agency-acceptance",
        ],
    }
    with TestClient(create_app(pilot_control=control)) as client:
        dry_run = client.post(
            "/api/v1/pilot/retention",
            headers=_headers(control, PilotRole.DATA_STEWARD),
            json=request,
        )
        assert dry_run.status_code == 200
        assert dry_run.json()["deleted_count"] == 0
        assert all(path.exists() for path in (old_file, new_file, held_file, receipt_file))
        dispositions = {
            item["artifact_id"]: item["disposition"] for item in dry_run.json()["decisions"]
        }
        assert dispositions == {
            "old-temporary": "delete",
            "new-temporary": "retain",
            "held-temporary": "retain",
            "agency-acceptance": "retain",
        }

        request["mode"] = "execute"
        request["approval_phrase"] = "EXECUTE PILOT RETENTION"
        steward_execute = client.post(
            "/api/v1/pilot/retention",
            headers=_headers(control, PilotRole.DATA_STEWARD),
            json=request,
        )
        assert steward_execute.status_code == 403
        assert old_file.exists()

        executed = client.post(
            "/api/v1/pilot/retention",
            headers=_headers(control, PilotRole.PILOT_ADMIN),
            json=request,
        )
        assert executed.status_code == 200
        assert executed.json()["deleted_count"] == 1
        assert not old_file.exists()
        assert new_file.exists() and held_file.exists() and receipt_file.exists()


def test_retention_rejects_path_traversal_and_wrong_approval(tmp_path: Path) -> None:
    control = _control(tmp_path)
    payload = {
        "mode": "execute",
        "approval_phrase": "wrong",
        "artifact_ids": ["outside-artifact"],
    }
    with TestClient(create_app(pilot_control=control)) as client:
        traversal = client.post(
            "/api/v1/pilot/retention",
            headers=_headers(control, PilotRole.PILOT_ADMIN),
            json=payload,
        )
        assert traversal.status_code == 403

        wrong_approval = client.post(
            "/api/v1/pilot/retention",
            headers=_headers(control, PilotRole.PILOT_ADMIN),
            json=payload,
        )
        assert wrong_approval.status_code == 403

        caller_metadata = {
            **payload,
            "mode": "dry_run",
            "approval_phrase": None,
            "artifacts": [
                {
                    "artifact_id": "outside-artifact",
                    "relative_path": "temporary/missing.txt",
                    "category": "temporary",
                    "created_at": "2020-01-01T00:00:00Z",
                    "legal_hold": False,
                }
            ],
        }
        category_substitution = client.post(
            "/api/v1/pilot/retention",
            headers=_headers(control, PilotRole.PILOT_ADMIN),
            json=caller_metadata,
        )
        assert category_substitution.status_code == 422


def test_deployment_monitoring_keeps_health_separate_from_data_freshness(
    tmp_path: Path,
) -> None:
    control = _control(tmp_path)
    repository = ArtifactRepository(RepositoryPaths(root=tmp_path / "empty-repository"))
    with TestClient(create_app(repository, pilot_control=control)) as client:
        health = client.get("/api/v1/health")
        monitoring = client.get(
            "/api/v1/pilot/monitoring",
            headers=_headers(control, PilotRole.COMMAND_VIEWER),
        )
    assert health.json()["service_status"] == "healthy"
    assert monitoring.status_code == 200
    assert monitoring.json()["service_health"] == "healthy"
    assert monitoring.json()["data_freshness_state"] == "unavailable"
    assert monitoring.json()["operational_status"] == "non_operational"


def test_deployment_monitoring_uses_exact_served_status_for_accepted_operation(
    tmp_path: Path,
) -> None:
    control = _control(tmp_path)
    repository = ArtifactRepository()
    official_status = repository.status().model_copy(
        update={
            "dataset_mode": DatasetMode.OFFICIAL_INPUT,
            "operational_status": OperationalStatus.AGENCY_OPERATIONAL,
            "study_area": "example_study_area",
            "data_version": "example-official-v1",
            "source_timestamp": datetime.fromisoformat(
                OFFICIAL_SOURCE_TIMESTAMP.replace("Z", "+00:00")
            ),
        }
    )
    artifact_manifest_sha256 = _bind_served_payload(control, official_status)
    identity = control.authenticate(f"Bearer {_token(control, PilotRole.PILOT_ADMIN)}")
    request = _acceptance_request()
    request["artifact_manifest_sha256"] = artifact_manifest_sha256
    receipt = control.sign_acceptance(
        AcceptanceReceiptRequest.model_validate(request),
        identity,
    )
    _install_receipt(control, receipt)
    repository.status = lambda: official_status  # type: ignore[method-assign]

    with TestClient(create_app(repository, pilot_control=control)) as client:
        response = client.get(
            "/api/v1/pilot/monitoring",
            headers=_headers(control, PilotRole.COMMAND_VIEWER),
        )

    assert response.status_code == 200
    assert response.json()["operational_status"] == "agency_operational"
    assert response.json()["deployment_state"] == "accepted_for_agency_operation"
    serialized = json.dumps(response.json()).lower()
    assert str(tmp_path).lower() not in serialized
    assert "\\users\\" not in serialized and "/users/" not in serialized


def test_environment_rejects_multi_worker_jsonl_audit_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "FLOODGUARD_PILOT_KEYS_JSON",
        json.dumps({KEY_ID: base64.b64encode(KEY).decode("ascii")}),
    )
    monkeypatch.setenv("FLOODGUARD_PILOT_ACTIVE_KEY_ID", KEY_ID)
    monkeypatch.setenv("FLOODGUARD_PILOT_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv(
        "FLOODGUARD_PILOT_AUDIT_ANCHOR",
        str(tmp_path / "audit-anchor.json"),
    )
    monkeypatch.setenv("FLOODGUARD_PILOT_AUDIT_WRITER_MODE", "single_process")
    monkeypatch.setenv("WEB_CONCURRENCY", "2")

    with pytest.raises(PilotConfigurationError, match="one API worker"):
        PilotControl.from_environment()


def test_explicit_audit_genesis_requires_both_preprovisioned_files(tmp_path: Path) -> None:
    control = _control(tmp_path)
    initial = control.audit.read()
    assert initial.chain_valid is True
    assert initial.entry_count == 0
    assert control.audit.path is not None
    assert control.audit.anchor_path is not None
    assert control.audit.path.parent != control.audit.anchor_path.parent
    anchor = json.loads(control.audit.anchor_path.read_text(encoding="utf-8"))
    assert anchor["entry_count"] == 0
    assert anchor["last_event_hash"] == "0" * 64

    control.audit.anchor_path.unlink()
    assert control.audit.state() == "invalid"
    fresh = PilotControl(
        keyring=control.keyring,
        audit_log_path=control.audit.path,
        audit_anchor_path=control.audit.anchor_path,
        clock=lambda: NOW,
    )
    assert fresh.audit.state() == "invalid"


@pytest.mark.parametrize("mutation", ["delete", "empty", "valid_prefix"])
def test_audit_anchor_rejects_ledger_rollback_across_restart(
    tmp_path: Path,
    mutation: str,
) -> None:
    control = _control(tmp_path / mutation)
    identity = control.authenticate(f"Bearer {_token(control, PilotRole.PILOT_ADMIN)}")
    for sequence in (1, 2):
        control.audit.append(
            identity=identity,
            action="rollback:test",
            outcome="completed",
            details={"sequence": sequence},
            now=NOW,
        )
    assert control.audit.path is not None
    assert control.audit.anchor_path is not None
    complete = control.audit.path.read_bytes()
    if mutation == "delete":
        control.audit.path.unlink()
    elif mutation == "empty":
        control.audit.path.write_bytes(b"")
    else:
        control.audit.path.write_bytes(complete.splitlines(keepends=True)[0])

    restarted = PilotControl(
        keyring=control.keyring,
        audit_log_path=control.audit.path,
        audit_anchor_path=control.audit.anchor_path,
        clock=lambda: NOW,
    )
    assert restarted.audit.state() == "invalid"
    with pytest.raises(PilotConfigurationError, match="Pilot audit"):
        restarted.audit.append(
            identity=identity,
            action="rollback:continue",
            outcome="completed",
            details={},
            now=NOW,
        )


def test_audit_append_rejects_path_substitution_before_descriptor_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control = _control(tmp_path)
    identity = control.authenticate(f"Bearer {_token(control, PilotRole.PILOT_ADMIN)}")
    assert control.audit.path is not None
    alternate = control.audit.path.with_name("substitute.jsonl")
    alternate.write_text("substituted bytes\n", encoding="utf-8")
    real_open = os.open
    real_replace = os.replace
    attacked = False

    def substitute_before_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        nonlocal attacked
        if not attacked and Path(path) == control.audit.path:
            attacked = True
            real_replace(alternate, control.audit.path)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", substitute_before_open)
    with pytest.raises(PilotConfigurationError, match="identity changed"):
        control.audit.append(
            identity=identity,
            action="substitution:test",
            outcome="completed",
            details={},
            now=NOW,
        )
    assert attacked is True
    assert control.audit.state() == "invalid"


def test_retention_root_must_remain_existing_regular_directory(tmp_path: Path) -> None:
    control = _control(tmp_path)
    assert control.retention.configured is True
    assert control.retention.root is not None
    root = control.retention.root
    moved = root.with_name("artifacts-moved")
    root.rename(moved)
    assert control.retention.configured is False

    regular_file = tmp_path / "not-a-directory"
    regular_file.write_text("file", encoding="utf-8")
    control.retention.root = regular_file
    assert control.retention.configured is False
    control.retention.root = tmp_path / "does-not-exist"
    assert control.retention.configured is False


@pytest.mark.parametrize(
    ("generated_at", "review_due_at"),
    [
        ("2026-06-15T10:00:00Z", "2026-07-15T10:00:00Z"),
        ("2026-07-17T10:00:00Z", "2026-07-18T10:00:00Z"),
    ],
)
def test_retention_catalog_future_or_stale_state_fails_closed(
    tmp_path: Path,
    generated_at: str,
    review_due_at: str,
) -> None:
    control = _control(tmp_path)
    assert control.retention.catalog_path is not None
    signed = json.loads(control.retention.catalog_path.read_text(encoding="utf-8"))
    payload = signed["payload"]
    payload["generated_at"] = generated_at
    payload["review_due_at"] = review_due_at
    _resign_retention_catalog(control, payload)
    assert control.retention.configured is False
    readiness = control.readiness(
        dataset_mode="fixture_demo",
        study_area="fixture_thailand_demo",
        data_version="fixture-2026-06-29-v1",
    )
    assert readiness.retention_state == "unconfigured"


def test_retention_catalog_requires_mandatory_evidence_and_standard_json(
    tmp_path: Path,
) -> None:
    missing_evidence = _control(tmp_path / "missing-evidence")
    assert missing_evidence.retention.catalog_path is not None
    signed = json.loads(missing_evidence.retention.catalog_path.read_text(encoding="utf-8"))
    payload = signed["payload"]
    payload["artifacts"] = []
    _resign_retention_catalog(missing_evidence, payload)
    assert missing_evidence.retention.configured is False

    non_finite = _control(tmp_path / "non-finite")
    assert non_finite.retention.catalog_path is not None
    catalog_text = non_finite.retention.catalog_path.read_text(encoding="utf-8")
    catalog_text = catalog_text.replace(
        '"generated_at":"2026-07-16T10:00:00Z"',
        '"generated_at":NaN',
        1,
    )
    assert "NaN" in catalog_text
    non_finite.retention.catalog_path.write_text(catalog_text, encoding="utf-8")
    assert non_finite.retention.configured is False


def test_retention_control_bindings_reject_copy_hash_and_path_substitution(
    tmp_path: Path,
) -> None:
    manifest_copy = _control(tmp_path / "manifest-copy")
    assert manifest_copy.current_artifact_manifest_path is not None
    copied_manifest = tmp_path / "copied-artifact-manifest.json"
    copied_manifest.write_bytes(manifest_copy.current_artifact_manifest_path.read_bytes())
    manifest_copy.current_artifact_manifest_path = copied_manifest
    assert (
        manifest_copy.readiness(
            dataset_mode="fixture_demo",
            study_area="fixture_thailand_demo",
            data_version="fixture-2026-06-29-v1",
        ).retention_state
        == "unconfigured"
    )

    audit_copy = _control(tmp_path / "audit-copy")
    assert audit_copy.audit.path is not None
    assert audit_copy.retention.root is not None
    assert audit_copy.retention.catalog_path is not None
    copied_ledger = audit_copy.retention.root / "audit" / "copied" / "pilot.jsonl"
    copied_ledger.parent.mkdir(parents=True)
    copied_ledger.write_bytes(audit_copy.audit.path.read_bytes())
    signed_catalog = json.loads(audit_copy.retention.catalog_path.read_text(encoding="utf-8"))
    ledger_entry = next(
        item
        for item in signed_catalog["payload"]["artifacts"]
        if item["artifact_id"] == "pilot-audit-ledger"
    )
    ledger_entry["relative_path"] = "audit/copied/pilot.jsonl"
    ledger_entry["sha256"] = hashlib.sha256(copied_ledger.read_bytes()).hexdigest()
    _resign_retention_catalog(audit_copy, signed_catalog["payload"])
    assert (
        audit_copy.readiness(
            dataset_mode="fixture_demo",
            study_area="fixture_thailand_demo",
            data_version="fixture-2026-06-29-v1",
        ).retention_state
        == "unconfigured"
    )

    hash_substitution = _control(tmp_path / "hash-substitution")
    assert hash_substitution.retention.catalog_path is not None
    signed_catalog = json.loads(
        hash_substitution.retention.catalog_path.read_text(encoding="utf-8")
    )
    field_entry = next(
        item
        for item in signed_catalog["payload"]["artifacts"]
        if item["artifact_id"] == "current-field-validation-receipt"
    )
    field_entry["evidence_binding_sha256"] = "0" * 64
    _resign_retention_catalog(hash_substitution, signed_catalog["payload"])
    assert (
        hash_substitution.readiness(
            dataset_mode="fixture_demo",
            study_area="fixture_thailand_demo",
            data_version="fixture-2026-06-29-v1",
        ).retention_state
        == "unconfigured"
    )

    acceptance_copy = _control(tmp_path / "acceptance-copy")
    identity = acceptance_copy.authenticate(
        f"Bearer {_token(acceptance_copy, PilotRole.PILOT_ADMIN)}"
    )
    receipt = acceptance_copy.sign_acceptance(
        AcceptanceReceiptRequest.model_validate(_acceptance_request()),
        identity,
    )
    _install_receipt(acceptance_copy, receipt)
    assert acceptance_copy.installed_receipt_path is not None
    copied_receipt = tmp_path / "copied-acceptance-receipt.json"
    copied_receipt.write_bytes(acceptance_copy.installed_receipt_path.read_bytes())
    acceptance_copy.installed_receipt_path = copied_receipt
    readiness = acceptance_copy.readiness(
        dataset_mode="official_input",
        study_area="example_study_area",
        data_version="example-official-v1",
        served_payload=OFFICIAL_PAYLOAD,
    )
    assert readiness.retention_state == "unconfigured"
    assert readiness.agency_operational_allowed is False


def test_retention_parent_swap_quarantines_and_does_not_delete_substitute(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_root = tmp_path / "governed"
    parent = artifact_root / "temporary"
    parent.mkdir(parents=True)
    target = parent / "old.tmp"
    target.write_bytes(b"catalogued artifact")
    artifact = {
        "artifact_id": "old-temporary",
        "relative_path": "temporary/old.tmp",
        "category": "temporary",
        "created_at": "2026-07-01T00:00:00Z",
        "legal_hold": False,
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }
    control = _control(
        tmp_path / "control",
        artifact_root=artifact_root,
        retention_artifacts=[artifact],
    )
    original_parent = artifact_root / "temporary-original"
    real_replace = os.replace
    attacked = False

    def swap_parent(source: object, destination: object) -> None:
        nonlocal attacked
        if not attacked and Path(source) == target:
            attacked = True
            real_replace(parent, original_parent)
            parent.mkdir()
            target.write_bytes(b"catalogued artifact")
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", swap_parent)
    response = control.retention.evaluate(
        RetentionRequest(
            mode="execute",
            artifact_ids=["old-temporary"],
            approval_phrase="EXECUTE PILOT RETENTION",
        ),
        now=NOW,
    )
    assert attacked is True
    assert response.deleted_count == 0
    assert response.decisions[0].disposition == "blocked"
    assert response.decisions[0].deleted is False
    assert (original_parent / "old.tmp").read_bytes() == b"catalogued artifact"
    quarantined = list((artifact_root / ".retention-quarantine").glob("*.pending"))
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == b"catalogued artifact"


def test_operational_response_requires_exact_manifest_membership_and_lineage(
    tmp_path: Path,
) -> None:
    control = _control(tmp_path)
    identity = control.authenticate(f"Bearer {_token(control, PilotRole.PILOT_ADMIN)}")
    _install_receipt(
        control,
        control.sign_acceptance(
            AcceptanceReceiptRequest.model_validate(_acceptance_request()),
            identity,
        ),
    )
    exact = dict(OFFICIAL_PAYLOAD)
    readiness = control.readiness(
        dataset_mode="official_input",
        study_area="example_study_area",
        data_version="example-official-v1",
        served_payload=exact,
    )
    assert readiness.agency_operational_allowed is True
    control.assert_operational_boundary(exact)

    for substituted in (
        {**exact, "source_timestamp": "2026-07-12T09:00:01Z"},
        {**exact, "data_version": "substituted-version"},
        {**exact, "unmanifested_field": "changed-response-bytes"},
    ):
        with pytest.raises(OperationalBoundaryError):
            control.assert_operational_boundary(substituted)
        assert (
            control.readiness(
                dataset_mode="official_input",
                study_area="example_study_area",
                data_version="example-official-v1",
                served_payload=substituted,
            ).agency_operational_allowed
            is False
        )
