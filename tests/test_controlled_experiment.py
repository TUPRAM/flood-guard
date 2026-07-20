from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pandas as pd
import pytest
import rasterio
from rasterio.transform import Affine

import floodguard.controlled_experiment as controlled
import floodguard.controlled_threshold as controlled_threshold
from floodguard.controlled_experiment import (
    ACQUISITION_COLUMNS,
    ACQUISITION_SCHEMA,
    CELL_GRID_COLUMNS,
    MODEL_CONTRACT_SCHEMAS,
    MODEL_EVIDENCE_COLUMNS,
    REQUIRED_MODEL_FAMILIES,
    ZERO_DIVISION_CONVENTION,
    ControlledExperimentError,
    VerifiedSpatialHoldout,
    assess_acquisition_manifest,
    build_gate_receipt,
    build_gate_report_markdown,
    compare_three_model_predictions,
    freeze_spatial_holdout,
    load_signed_reference_cell_evidence,
    load_spatial_holdout,
    run_controlled_three_model_experiment,
    write_acquisition_authority_receipt,
    write_gate_report,
    write_signed_reference_cell_receipt,
    write_signed_model_run_manifest,
)
from floodguard.model_promotion import (
    REQUIRED_ERROR_CATEGORIES,
    write_signed_model_promotion_policy,
)
from floodguard.controlled_threshold import write_signed_threshold_selection_receipt


UTC = timezone.utc
SHA_A = "a" * 64
SHA_B = "b" * 64
KEY_ID = "test-authority-v1"
SIGNING_KEY = b"floodguard-test-signing-key-32-bytes-minimum"
REVIEWER_KEY_ID = "test-reviewer-authority-v1"
REVIEWER_KEY = b"floodguard-test-reviewer-key-32-bytes-minimum"
ADJUDICATOR_KEY_ID = "test-adjudicator-authority-v1"
ADJUDICATOR_KEY = b"floodguard-test-adjudicator-key-32-bytes"
HOLDOUT_KEY_ID = "test-holdout-custodian-v1"
HOLDOUT_KEY = b"floodguard-test-holdout-key-32-bytes-minimum"
REFERENCE_KEY_ID = "test-reference-authority-v1"
REFERENCE_KEY = b"floodguard-test-reference-key-32-bytes-minimum"
POLICY_KEY_ID = "test-promotion-policy-v1"
POLICY_KEY = b"floodguard-test-policy-key-32-bytes-minimum"
EXECUTION_KEY_ID = "test-execution-authority-v1"
EXECUTION_KEY = b"floodguard-test-execution-key-32-bytes-minimum"
MODEL_KEY_ID = "test-model-executor-v1"
MODEL_KEY = b"floodguard-test-model-key-32-bytes-minimum"
RESULT_KEY_ID = "test-result-authority-v1"
RESULT_KEY = b"floodguard-test-result-key-32-bytes-minimum"
EXTERNAL_KEY_ID = "test-external-data-authority-ed25519-v1"
EXTERNAL_SEED = bytes(range(32))


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
            hashlib.sha512(r_encoded + public_key + message).digest(), "little"
        )
        % controlled._ED25519_ORDER
    )
    scalar_signature = (nonce + challenge * scalar) % controlled._ED25519_ORDER
    return r_encoded + scalar_signature.to_bytes(32, "little")


EXTERNAL_PUBLIC_KEY = _ed25519_public_key(EXTERNAL_SEED)
EXTERNAL_PUBLIC_KEYS = {EXTERNAL_KEY_ID: EXTERNAL_PUBLIC_KEY}
SIGNING_KEYS = {
    KEY_ID: SIGNING_KEY,
    REVIEWER_KEY_ID: REVIEWER_KEY,
    ADJUDICATOR_KEY_ID: ADJUDICATOR_KEY,
    HOLDOUT_KEY_ID: HOLDOUT_KEY,
    REFERENCE_KEY_ID: REFERENCE_KEY,
    POLICY_KEY_ID: POLICY_KEY,
    EXECUTION_KEY_ID: EXECUTION_KEY,
    MODEL_KEY_ID: MODEL_KEY,
    RESULT_KEY_ID: RESULT_KEY,
}


def test_ed25519_verifier_matches_rfc8032_vector_one() -> None:
    public_key = bytes.fromhex(
        "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
    )
    signature = bytes.fromhex(
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
        "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
    )

    assert controlled._ed25519_verify(public_key, signature, b"") is True
    tampered = bytearray(signature)
    tampered[-1] ^= 1
    assert controlled._ed25519_verify(public_key, bytes(tampered), b"") is False


def test_unchanged_completed_authority_template_cannot_authorize_processing() -> None:
    template_path = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "controlled-experiment"
        / "external_authority_completed_decision.template.json"
    )
    template = json.loads(template_path.read_text(encoding="utf-8"))

    with pytest.raises(ControlledExperimentError):
        controlled._validate_external_authority_decision_payload(
            template,
            manifest_sha256="a" * 64,
            experiment_id="mae_sai_2024_controlled_three_model_v1",
            study_area="Chiang Rai / Mae Sai 2024",
            expected_rows={},
            external_authority_public_keys=EXTERNAL_PUBLIC_KEYS,
            signature=b"\x00" * 64,
            verified_at_utc=datetime(2026, 7, 20, tzinfo=UTC),
        )


def test_editable_acquisition_csv_cannot_self_authorize(tmp_path: Path) -> None:
    manifest, artifacts = _acquisition_fixture(tmp_path, base_ready=True)

    assessment = assess_acquisition_manifest(manifest, artifact_paths=artifacts)

    assert assessment.ready is False
    assert assessment.authority_receipt_sha256 is None
    assert assessment.blockers == (
        "acquisition_authority: externally signed product-specific authority "
        "decision and internal integrity receipt are missing",
    )


def test_signed_acquisition_authority_binds_products_permissions_and_bytes(
    tmp_path: Path,
) -> None:
    manifest, artifacts, authority, assessment = _authorized_acquisition(tmp_path)

    assert assessment.ready is True
    assert assessment.blockers == ()
    assert assessment.authority_receipt_sha256 == _sha(authority)
    assert set(dict(assessment.sha256_by_role)) == {
        "pre_event_sar",
        "post_event_sar",
        "reference_mask",
    }

    payload = json.loads(authority.read_text(encoding="utf-8"))
    assert (
        payload["external_authority_decision_id"]
        == payload["external_authority_decision"]["decision_id"]
    )
    assert "allowlist_id" not in payload
    payload["authorizations"][0]["product_id"] = "SUBSTITUTED"
    authority.write_text(json.dumps(payload), encoding="utf-8")
    blocked = assess_acquisition_manifest(
        manifest,
        artifact_paths=artifacts,
        authority_receipt_path=authority,
        signing_keys=SIGNING_KEYS,
        external_authority_public_keys=EXTERNAL_PUBLIC_KEYS,
        verified_at_utc=datetime(2024, 1, 5, tzinfo=UTC),
    )
    assert blocked.ready is False
    assert any("HMAC signature is invalid" in item for item in blocked.blockers)


def _rewrite_authority_receipt(
    authority: Path,
    mutate: object,
    *,
    resign_external: bool,
) -> None:
    payload = json.loads(authority.read_text(encoding="utf-8"))
    decision = payload["external_authority_decision"]
    mutate(decision, payload)
    payload["authorizations"] = decision["products"]
    if resign_external:
        payload["external_authority_signature_base64"] = base64.b64encode(
            _ed25519_sign(EXTERNAL_SEED, controlled._canonical_json_bytes(decision))
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
        signing_key_id=KEY_ID,
        signing_key=SIGNING_KEY,
        self_hash_field="manifest_sha256",
    )
    authority.write_text(json.dumps(resealed), encoding="utf-8")


@pytest.mark.parametrize(
    ("mutation", "resign_external", "message"),
    [
        (
            lambda decision, _receipt: decision["products"][0].__setitem__(
                "product_id", "SUBSTITUTED-PRODUCT"
            ),
            False,
            "product_id was substituted",
        ),
        (
            lambda decision, _receipt: decision["authorized_signer"].__setitem__(
                "name", " "
            ),
            True,
            "must not be blank",
        ),
        (
            lambda decision, receipt: receipt.__setitem__(
                "external_authority_signature_base64",
                base64.b64encode(b"x" * 64).decode("ascii"),
            ),
            False,
            "detached Ed25519 signature is invalid",
        ),
        (
            lambda decision, _receipt: decision["products"][0][
                "permissions"
            ].__setitem__("validation_metrics", False),
            True,
            "every required external permission",
        ),
        (
            lambda decision, _receipt: decision["authorized_signer"].__setitem__(
                "decision_expires_at_utc", "2024-01-04T00:00:00Z"
            ),
            True,
            "expired, premature, or not yet valid",
        ),
    ],
)
def test_external_authority_decision_fails_closed_under_substitution(
    tmp_path: Path,
    mutation: object,
    resign_external: bool,
    message: str,
) -> None:
    manifest, artifacts, authority, _assessment = _authorized_acquisition(tmp_path)
    _rewrite_authority_receipt(
        authority,
        mutation,
        resign_external=resign_external,
    )

    blocked = assess_acquisition_manifest(
        manifest,
        artifact_paths=artifacts,
        authority_receipt_path=authority,
        signing_keys=SIGNING_KEYS,
        external_authority_public_keys=EXTERNAL_PUBLIC_KEYS,
        verified_at_utc=datetime(2024, 1, 5, tzinfo=UTC),
    )

    assert blocked.ready is False
    assert any(message in blocker for blocker in blocked.blockers)


def test_external_authority_requires_runtime_trusted_public_key(
    tmp_path: Path,
) -> None:
    manifest, artifacts, authority, _assessment = _authorized_acquisition(tmp_path)

    blocked = assess_acquisition_manifest(
        manifest,
        artifact_paths=artifacts,
        authority_receipt_path=authority,
        signing_keys=SIGNING_KEYS,
        external_authority_public_keys={},
        verified_at_utc=datetime(2024, 1, 5, tzinfo=UTC),
    )

    assert blocked.ready is False
    assert any("public key is not trusted" in item for item in blocked.blockers)


def test_acquisition_assessment_cannot_be_directly_forged(tmp_path: Path) -> None:
    _manifest, _artifacts, _authority, assessment = _authorized_acquisition(tmp_path)

    with pytest.raises(ControlledExperimentError, match="verified manifest path"):
        controlled.AcquisitionGateAssessment(
            experiment_id=assessment.experiment_id,
            study_area=assessment.study_area,
            manifest_sha256=assessment.manifest_sha256,
            manifest_file_sha256=assessment.manifest_file_sha256,
            sha256_by_role=assessment.sha256_by_role,
            authority_receipt_sha256=assessment.authority_receipt_sha256,
            authority_signing_key_id=assessment.authority_signing_key_id,
            authority_issued_at_utc=assessment.authority_issued_at_utc,
            authority_expires_at_utc=assessment.authority_expires_at_utc,
            ready=True,
            blockers=(),
            external_authority_signing_key_id=(
                assessment.external_authority_signing_key_id
            ),
            external_authority_decision_sha256=(
                assessment.external_authority_decision_sha256
            ),
            _verification_marker=object(),
        )


def test_acquisition_byte_substitution_and_unresolved_truth_fail_closed(
    tmp_path: Path,
) -> None:
    manifest, artifacts = _acquisition_fixture(tmp_path / "bytes", base_ready=True)
    artifacts["post_event_sar"].write_bytes(b"substituted")
    with pytest.raises(ControlledExperimentError, match="attempts to override"):
        assess_acquisition_manifest(manifest, artifact_paths=artifacts)

    manifest, artifacts = _acquisition_fixture(
        tmp_path / "truth",
        base_ready=False,
    )
    base = assess_acquisition_manifest(manifest, artifact_paths=artifacts)
    with pytest.raises(ControlledExperimentError, match="base gates are blocked"):
        _issue_authority(tmp_path / "truth", manifest, base)


def test_acquisition_rejects_private_path_and_invalid_authority_key(
    tmp_path: Path,
) -> None:
    manifest, artifacts, authority, _assessment = _authorized_acquisition(tmp_path)
    frame = pd.read_csv(manifest)
    frame.loc[frame["role"].eq("reference_mask"), "local_path_hint"] = (
        r"C:\private\mask.tif"
    )
    frame.to_csv(manifest, index=False, lineterminator="\n")
    with pytest.raises(ControlledExperimentError, match="redacted"):
        assess_acquisition_manifest(manifest, artifact_paths=artifacts)

    manifest, artifacts, authority, _assessment = _authorized_acquisition(
        tmp_path / "wrong-key"
    )
    blocked = assess_acquisition_manifest(
        manifest,
        artifact_paths=artifacts,
        authority_receipt_path=authority,
        signing_keys={"other": SIGNING_KEY},
        external_authority_public_keys=EXTERNAL_PUBLIC_KEYS,
        verified_at_utc=datetime(2024, 1, 5, tzinfo=UTC),
    )
    assert blocked.ready is False
    assert any("not trusted at runtime" in item for item in blocked.blockers)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("product_id", "", "product_id must not be blank"),
        ("product_id", "unsafe/product", "stable product identifier"),
        ("source_name", " ", "source_name must not be blank"),
        ("assumptions", "", "assumptions must not be blank"),
        ("acquisition_start_utc", "not-a-time", "must be ISO-8601"),
        ("acquisition_end_utc", "2024-01-02T00:01:00", "must include a timezone"),
        ("source_timestamp", "", "source_timestamp must not be blank"),
        ("source_timestamp", "2024-01-01T00:00:00Z", "outside the acquisition"),
    ],
)
def test_acquisition_rejects_missing_or_malformed_identity_and_timestamps(
    tmp_path: Path,
    field: str,
    value: str,
    message: str,
) -> None:
    manifest, artifacts = _acquisition_fixture(tmp_path, base_ready=True)
    frame = pd.read_csv(manifest)
    frame.loc[frame["role"].eq("post_event_sar"), field] = value
    frame.to_csv(manifest, index=False, lineterminator="\n")

    with pytest.raises(ControlledExperimentError, match=message):
        assess_acquisition_manifest(manifest, artifact_paths=artifacts)


def test_acquisition_authority_binds_source_identity_and_all_timestamps(
    tmp_path: Path,
) -> None:
    manifest, artifacts, authority, _assessment = _authorized_acquisition(tmp_path)
    original_authority_sha = _sha(authority)
    frame = pd.read_csv(manifest)
    frame.loc[frame["role"].eq("post_event_sar"), "source_timestamp"] = (
        "2024-01-02T00:00:30Z"
    )
    frame.to_csv(manifest, index=False, lineterminator="\n")

    blocked = assess_acquisition_manifest(
        manifest,
        artifact_paths=artifacts,
        authority_receipt_path=authority,
        signing_keys=SIGNING_KEYS,
        external_authority_public_keys=EXTERNAL_PUBLIC_KEYS,
        verified_at_utc=datetime(2024, 1, 5, tzinfo=UTC),
    )
    assert blocked.ready is False
    assert blocked.authority_receipt_sha256 is None
    assert any(
        "authority manifest was substituted" in item for item in blocked.blockers
    )
    assert _sha(authority) == original_authority_sha


def test_acquisition_authority_preserves_and_binds_subsecond_timestamps(
    tmp_path: Path,
) -> None:
    manifest, artifacts = _acquisition_fixture(tmp_path, base_ready=True)
    frame = pd.read_csv(manifest)
    post = frame["role"].eq("post_event_sar")
    frame.loc[post, "acquisition_start_utc"] = "2024-01-02T00:00:00.123456Z"
    frame.loc[post, "acquisition_end_utc"] = "2024-01-02T00:01:00.123456Z"
    frame.loc[post, "source_timestamp"] = "2024-01-02T00:00:00.123456Z"
    frame.to_csv(manifest, index=False, lineterminator="\n")
    base = assess_acquisition_manifest(manifest, artifact_paths=artifacts)
    authority = _issue_authority(tmp_path, manifest, base)

    payload = json.loads(authority.read_text(encoding="utf-8"))
    authorization = next(
        row for row in payload["authorizations"] if row["role"] == "post_event_sar"
    )
    assert authorization["acquisition_start_utc"].endswith(".123456Z")
    assert authorization["acquisition_end_utc"].endswith(".123456Z")
    assert authorization["source_timestamp"].endswith(".123456Z")

    frame.loc[post, "source_timestamp"] = "2024-01-02T00:00:00.654321Z"
    frame.to_csv(manifest, index=False, lineterminator="\n")
    blocked = assess_acquisition_manifest(
        manifest,
        artifact_paths=artifacts,
        authority_receipt_path=authority,
        signing_keys=SIGNING_KEYS,
        external_authority_public_keys=EXTERNAL_PUBLIC_KEYS,
        verified_at_utc=datetime(2024, 1, 5, tzinfo=UTC),
    )
    assert blocked.ready is False
    assert any(
        "authority manifest was substituted" in item for item in blocked.blockers
    )


def test_authority_hash_and_parser_use_one_exact_byte_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, artifacts, authority, _assessment = _authorized_acquisition(tmp_path)
    original = authority.read_bytes()
    original_sha = hashlib.sha256(original).hexdigest()
    alternate = json.dumps({"substituted": True}).encode()
    parse = controlled._json_object_bytes

    def swap_after_snapshot(content: bytes, label: str) -> dict[str, object]:
        payload = parse(content, label)
        if label == "acquisition authority receipt":
            authority.write_bytes(alternate)
        return payload

    monkeypatch.setattr(controlled, "_json_object_bytes", swap_after_snapshot)
    assessment = assess_acquisition_manifest(
        manifest,
        artifact_paths=artifacts,
        authority_receipt_path=authority,
        signing_keys=SIGNING_KEYS,
        external_authority_public_keys=EXTERNAL_PUBLIC_KEYS,
        verified_at_utc=datetime(2024, 1, 5, tzinfo=UTC),
    )
    assert assessment.ready is True
    assert assessment.authority_receipt_sha256 == original_sha
    assert authority.read_bytes() == alternate
    authority.write_bytes(original)


def test_descriptor_snapshot_rejects_detected_mid_read_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "receipt.json"
    target.write_bytes(b'{"original":true}\n')
    original_open = controlled._open_stable_binary

    class MutatingReader:
        def __init__(self, stream: object) -> None:
            self.stream = stream

        def fileno(self) -> int:
            return self.stream.fileno()

        def read(self, *args: object) -> bytes:
            content = self.stream.read(*args)
            target.write_bytes(b'{"mutated":true,"longer":true}\n')
            return content

    @contextmanager
    def attacked_open(path: Path, label: str):
        with original_open(path, label) as stream:
            yield MutatingReader(stream)

    monkeypatch.setattr(controlled, "_open_stable_binary", attacked_open)
    with pytest.raises(
        ControlledExperimentError, match="changed while its bytes were read"
    ):
        controlled._read_stable_bytes(target, "test receipt")


def test_holdout_signature_membership_and_geometry_are_all_bound(
    tmp_path: Path,
) -> None:
    _manifest, _artifacts, _authority, acquisition = _authorized_acquisition(
        tmp_path / "acquisition"
    )
    holdout, geometry, grid_contract, membership, receipt = _holdout_fixture(
        tmp_path / "holdout", acquisition=acquisition
    )

    loaded = load_spatial_holdout(
        receipt,
        geometry,
        grid_contract,
        membership,
        acquisition=acquisition,
        signing_keys=SIGNING_KEYS,
    )
    assert loaded == holdout
    assert [item.cell_id for item in loaded.memberships] == [
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
        "C6",
    ]
    assert loaded.receipt["cell_area_m2"] == 2500.0
    assert loaded.receipt["training_ids"] == ["TRAIN-A"]
    assert loaded.receipt["calibration_ids"] == ["CALIBRATION-B"]
    assert loaded.receipt["final_holdout_ids"] == ["FINAL-HOLDOUT-C"]
    assert loaded.receipt["acquisition_manifest_sha256"] == (
        acquisition.manifest_sha256
    )
    assert loaded.receipt["acquisition_authority_receipt_sha256"] == (
        acquisition.authority_receipt_sha256
    )
    assert loaded.receipt["acquisition_authority_signing_key_id"] == (
        acquisition.authority_signing_key_id
    )
    assert loaded.receipt["external_authority_decision_sha256"] == (
        acquisition.external_authority_decision_sha256
    )
    assert loaded.receipt["external_authority_signing_key_id"] == (
        acquisition.external_authority_signing_key_id
    )
    assert "source_registry_sha256" not in loaded.receipt
    assert loaded.training_partition_sha256
    assert loaded.calibration_partition_sha256
    assert loaded.final_holdout_partition_sha256
    assert (
        len(
            {
                loaded.training_partition_sha256,
                loaded.calibration_partition_sha256,
                loaded.final_holdout_partition_sha256,
            }
        )
        == 3
    )
    partition_cells = {
        split: {item.cell_id for item in loaded.memberships if item.split == split}
        for split in ("train", "calibration", "final_holdout")
    }
    assert all(partition_cells.values())
    assert partition_cells["train"].isdisjoint(partition_cells["calibration"])
    assert partition_cells["train"].isdisjoint(partition_cells["final_holdout"])
    assert partition_cells["calibration"].isdisjoint(partition_cells["final_holdout"])

    with pytest.raises(ControlledExperimentError, match="not trusted at runtime"):
        load_spatial_holdout(
            receipt,
            geometry,
            grid_contract,
            membership,
            acquisition=acquisition,
            signing_keys={"wrong": SIGNING_KEY},
        )

    membership_bytes = membership.read_bytes()
    membership_frame = pd.read_csv(membership)
    membership_frame.loc[membership_frame["cell_id"].eq("C3"), "split"] = "train"
    membership_frame.to_csv(membership, index=False, lineterminator="\n")
    with pytest.raises(ControlledExperimentError, match="membership SHA-256"):
        load_spatial_holdout(
            receipt,
            geometry,
            grid_contract,
            membership,
            acquisition=acquisition,
            signing_keys=SIGNING_KEYS,
        )
    membership.write_bytes(membership_bytes)

    payload = json.loads(geometry.read_text(encoding="utf-8"))
    payload["features"][1]["geometry"]["coordinates"][0][1][1] = 10
    geometry.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ControlledExperimentError, match="SHA-256"):
        load_spatial_holdout(
            receipt,
            geometry,
            grid_contract,
            membership,
            acquisition=acquisition,
            signing_keys=SIGNING_KEYS,
        )


def test_holdout_rejects_same_scope_different_acquisition_substitution(
    tmp_path: Path,
) -> None:
    _manifest, artifacts, _authority, acquisition = _authorized_acquisition(
        tmp_path / "acquisition-a"
    )
    holdout, geometry, grid_contract, membership, receipt = _holdout_fixture(
        tmp_path / "holdout", acquisition=acquisition
    )

    manifest_b, artifacts_b = _acquisition_fixture(
        tmp_path / "acquisition-b", base_ready=True
    )
    artifacts_b["pre_event_sar"].write_bytes(b"different-pre-event-product")
    frame_b = pd.read_csv(manifest_b)
    pre_selector = frame_b["role"].eq("pre_event_sar")
    frame_b.loc[pre_selector, "product_id"] = "PRODUCT-pre_event_sar-V2"
    frame_b.loc[pre_selector, "sha256"] = _sha(artifacts_b["pre_event_sar"])
    frame_b.to_csv(manifest_b, index=False, lineterminator="\n")
    base_b = assess_acquisition_manifest(manifest_b, artifact_paths=artifacts_b)
    authority_b = _issue_authority(tmp_path / "acquisition-b", manifest_b, base_b)
    acquisition_b = assess_acquisition_manifest(
        manifest_b,
        artifact_paths=artifacts_b,
        authority_receipt_path=authority_b,
        signing_keys=SIGNING_KEYS,
        external_authority_public_keys=EXTERNAL_PUBLIC_KEYS,
        verified_at_utc=datetime(2024, 1, 5, tzinfo=UTC),
    )
    assert acquisition_b.experiment_id == acquisition.experiment_id
    assert acquisition_b.study_area == acquisition.study_area
    assert acquisition_b.manifest_sha256 != acquisition.manifest_sha256

    with pytest.raises(
        ControlledExperimentError,
        match="acquisition_manifest_sha256 was substituted across acquisitions",
    ):
        load_spatial_holdout(
            receipt,
            geometry,
            grid_contract,
            membership,
            acquisition=acquisition_b,
            signing_keys=SIGNING_KEYS,
        )

    substituted_authority = replace(
        acquisition,
        authority_receipt_sha256="e" * 64,
        external_authority_decision_sha256="f" * 64,
    )
    with pytest.raises(
        ControlledExperimentError,
        match="acquisition_authority_receipt_sha256 was substituted",
    ):
        load_spatial_holdout(
            receipt,
            geometry,
            grid_contract,
            membership,
            acquisition=substituted_authority,
            signing_keys=SIGNING_KEYS,
        )

    bundle = _reference_bundle_fixture(
        tmp_path / "reference",
        acquisition,
        holdout,
        artifacts["reference_mask"],
    )
    with pytest.raises(
        ControlledExperimentError,
        match="acquisition_manifest_sha256 was substituted across acquisitions",
    ):
        controlled._verify_execution_prerequisites(
            acquisition=acquisition_b,
            reviewer_qualification=bundle["reviewer"],
            holdout=holdout,
            reference_cells=bundle["reference"],
        )


def test_holdout_requires_ready_authority_valid_at_declared_freeze(
    tmp_path: Path,
) -> None:
    manifest, artifacts = _acquisition_fixture(tmp_path / "unready", base_ready=True)
    unready = assess_acquisition_manifest(manifest, artifact_paths=artifacts)
    geometry = _holdout_geojson(tmp_path / "holdout")
    grid = _cell_grid(tmp_path / "holdout")

    with pytest.raises(ControlledExperimentError, match="ready signed acquisition"):
        freeze_spatial_holdout(
            geometry,
            acquisition=unready,
            grid_contract_path=grid.with_name("grid-contract.json"),
            cell_grid_path=grid,
            membership_output_path=tmp_path / "holdout" / "unready-membership.csv",
            target_crs="EPSG:6933",
            grid_contract_sha256=_sha(grid.with_name("grid-contract.json")),
            frozen_at_utc=datetime(2024, 1, 4, tzinfo=UTC),
            assumptions="Synthetic contract fixture.",
            signing_key_id=HOLDOUT_KEY_ID,
            signing_key=HOLDOUT_KEY,
            output_path=tmp_path / "holdout" / "unready-receipt.json",
        )

    _manifest, _artifacts, _authority, acquisition = _authorized_acquisition(
        tmp_path / "authorized"
    )
    with pytest.raises(
        ControlledExperimentError, match="outside acquisition authority validity"
    ):
        freeze_spatial_holdout(
            geometry,
            acquisition=acquisition,
            grid_contract_path=grid.with_name("grid-contract.json"),
            cell_grid_path=grid,
            membership_output_path=tmp_path / "holdout" / "expired-membership.csv",
            target_crs="EPSG:6933",
            grid_contract_sha256=_sha(grid.with_name("grid-contract.json")),
            frozen_at_utc=datetime(2031, 1, 1, tzinfo=UTC),
            assumptions="Synthetic contract fixture.",
            signing_key_id=HOLDOUT_KEY_ID,
            signing_key=HOLDOUT_KEY,
            output_path=tmp_path / "holdout" / "expired-receipt.json",
        )


def test_holdout_rejects_non_equal_area_crs_overlap_and_outside_cells(
    tmp_path: Path,
) -> None:
    _manifest, _artifacts, _authority, acquisition = _authorized_acquisition(
        tmp_path / "acquisition"
    )
    geometry = _holdout_geojson(tmp_path / "crs")
    grid = _cell_grid(tmp_path / "crs")
    with pytest.raises(ControlledExperimentError, match="equal-area"):
        freeze_spatial_holdout(
            geometry,
            acquisition=acquisition,
            grid_contract_path=tmp_path / "crs" / "grid-contract.json",
            cell_grid_path=grid,
            membership_output_path=tmp_path / "crs" / "membership.csv",
            target_crs="EPSG:32647",
            grid_contract_sha256=_sha(tmp_path / "crs" / "grid-contract.json"),
            frozen_at_utc=datetime(2024, 1, 4, tzinfo=UTC),
            assumptions="Synthetic contract fixture.",
            signing_key_id=HOLDOUT_KEY_ID,
            signing_key=HOLDOUT_KEY,
            output_path=tmp_path / "crs" / "receipt.json",
        )

    geometry = _holdout_geojson(tmp_path / "overlap")
    payload = json.loads(geometry.read_text(encoding="utf-8"))
    payload["features"][1]["geometry"]["coordinates"] = [
        [[50, 0], [150, 0], [150, 100], [50, 100], [50, 0]]
    ]
    geometry.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ControlledExperimentError, match="interiors overlap"):
        _freeze_paths(tmp_path / "overlap", geometry, _cell_grid(tmp_path / "overlap"))

    geometry = _holdout_geojson(tmp_path / "outside")
    payload = json.loads(geometry.read_text(encoding="utf-8"))
    payload["features"][1]["geometry"]["coordinates"] = [
        [[100, 0], [150, 0], [150, 100], [100, 100], [100, 0]]
    ]
    geometry.write_text(json.dumps(payload), encoding="utf-8")
    grid = _cell_grid(tmp_path / "outside")
    with pytest.raises(ControlledExperimentError, match="outside all polygons"):
        _freeze_paths(tmp_path / "outside", geometry, grid)


def test_holdout_requires_nonempty_three_way_polygon_and_cell_partitions(
    tmp_path: Path,
) -> None:
    geometry = _holdout_geojson(tmp_path / "missing-calibration")
    payload = json.loads(geometry.read_text(encoding="utf-8"))
    payload["features"][1]["properties"]["split"] = "train"
    geometry.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ControlledExperimentError, match="non-empty train, calibration"):
        _freeze_paths(
            tmp_path / "missing-calibration",
            geometry,
            _cell_grid(tmp_path / "missing-calibration"),
        )

    geometry = _holdout_geojson(tmp_path / "legacy-holdout-label")
    payload = json.loads(geometry.read_text(encoding="utf-8"))
    payload["features"][1]["properties"]["split"] = "holdout"
    geometry.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ControlledExperimentError, match="train, calibration, or"):
        _freeze_paths(
            tmp_path / "legacy-holdout-label",
            geometry,
            _cell_grid(tmp_path / "legacy-holdout-label"),
        )

    geometry = _holdout_geojson(tmp_path / "empty-calibration-cells")
    payload = json.loads(geometry.read_text(encoding="utf-8"))
    payload["features"][1]["geometry"]["coordinates"] = [
        [[100, 0], [110, 0], [110, 100], [100, 100], [100, 0]]
    ]
    payload["features"][2]["geometry"]["coordinates"] = [
        [[110, 0], [300, 0], [300, 100], [110, 100], [110, 0]]
    ]
    geometry.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ControlledExperimentError, match="non-empty train, calibration"):
        _freeze_paths(
            tmp_path / "empty-calibration-cells",
            geometry,
            _cell_grid(tmp_path / "empty-calibration-cells"),
        )


def test_grid_area_is_affine_derived_and_substitutions_fail_closed(
    tmp_path: Path,
) -> None:
    _manifest, _artifacts, _authority, acquisition = _authorized_acquisition(
        tmp_path / "acquisition"
    )
    geometry = _holdout_geojson(tmp_path)
    grid = _cell_grid(tmp_path)
    frame = pd.read_csv(grid)
    frame["cell_area_m2"] = 999999.0
    frame.to_csv(grid, index=False, lineterminator="\n")
    with pytest.raises(ControlledExperimentError, match="affine determinant"):
        _freeze_paths(tmp_path, geometry, grid, acquisition=acquisition)

    frame["cell_area_m2"] = 2500.0
    frame.to_csv(grid, index=False, lineterminator="\n")
    holdout = _freeze_paths(tmp_path, geometry, grid, acquisition=acquisition)
    assert holdout.receipt["cell_area_m2"] == 2500.0

    contract_path = tmp_path / "grid-contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["transform"][0] = 100.0
    contract_path.write_text(json.dumps(contract, sort_keys=True), encoding="utf-8")
    with pytest.raises(ControlledExperimentError, match="Grid contract SHA-256"):
        load_spatial_holdout(
            tmp_path / "holdout-receipt.json",
            geometry,
            contract_path,
            tmp_path / "membership.csv",
            acquisition=acquisition,
            signing_keys=SIGNING_KEYS,
        )


def test_grid_contract_requires_exact_membership_and_affine_centers(
    tmp_path: Path,
) -> None:
    _manifest, _artifacts, _authority, acquisition = _authorized_acquisition(
        tmp_path / "acquisition"
    )
    geometry = _holdout_geojson(tmp_path)
    grid = _cell_grid(tmp_path)
    frame = pd.read_csv(grid)
    frame.loc[frame["cell_id"].eq("C4"), "x"] = 176.0
    frame.to_csv(grid, index=False, lineterminator="\n")
    with pytest.raises(ControlledExperimentError, match="affine-derived cell centers"):
        _freeze_paths(tmp_path, geometry, grid, acquisition=acquisition)

    frame = frame.loc[~frame["cell_id"].eq("C4")].copy()
    frame.loc[frame["cell_id"].eq("C3"), "x"] = 125.0
    frame.to_csv(grid, index=False, lineterminator="\n")
    with pytest.raises(ControlledExperimentError, match="exactly cover"):
        _freeze_paths(tmp_path, geometry, grid, acquisition=acquisition)


def test_verified_holdout_rejects_in_memory_substitution(tmp_path: Path) -> None:
    holdout, _geometry, _grid, _membership, _receipt = _holdout_fixture(tmp_path)

    holdout.receipt["cell_count"] = 999
    with pytest.raises(
        ControlledExperimentError, match="receipt was mutated in memory"
    ):
        controlled._verify_holdout_instance(holdout)

    fresh, _geometry, _grid, _membership, _receipt = _holdout_fixture(
        tmp_path / "membership"
    )
    substituted = replace(fresh, memberships=fresh.memberships[:-1])
    with pytest.raises(
        ControlledExperimentError, match="membership count was substituted"
    ):
        controlled._verify_holdout_instance(substituted)


def test_comparison_uses_frozen_membership_and_physical_area(tmp_path: Path) -> None:
    holdout, reference = _comparison_fixture(tmp_path)

    metrics, calibration, errors = compare_three_model_predictions(
        _prediction_frames(),
        holdout,
        reference_cells=reference,
        thresholds=_thresholds(),
        calibration_bins=4,
    )

    assert set(metrics["model_family"]) == set(REQUIRED_MODEL_FAMILIES)
    assert {
        "iou",
        "f1_dice",
        "precision",
        "recall",
        "predicted_area_m2",
        "reference_area_m2",
        "area_error_m2",
        "absolute_area_error_m2",
        "area_error_ratio",
        "brier_score",
        "expected_calibration_error",
    }.issubset(metrics.columns)
    deterministic = metrics.set_index("model_family").loc["deterministic_sar_baseline"]
    assert deterministic["predicted_area_m2"] == 5000.0
    assert deterministic["reference_area_m2"] == 2500.0
    assert deterministic["area_error_m2"] == 2500.0
    assert deterministic["area_error_ratio"] == 1.0
    assert len(calibration) == 12
    assert metrics["evaluation_split"].eq("untouched_final_spatial_holdout").all()
    assert set(errors["category"]) == {"all", *controlled.ERROR_STRATA}
    assert not metrics["can_feed_decision_layer"].any()

    changed_calibration = _prediction_frames()
    for frame in changed_calibration.values():
        mask = frame["split"].eq("calibration")
        frame.loc[mask, "probability_0_1"] = [0.99, 0.01]
    repeated_metrics, repeated_calibration, repeated_errors = (
        compare_three_model_predictions(
            changed_calibration,
            holdout,
            reference_cells=reference,
            thresholds=_thresholds(),
            calibration_bins=4,
        )
    )
    pd.testing.assert_frame_equal(metrics, repeated_metrics)
    pd.testing.assert_frame_equal(calibration, repeated_calibration)
    pd.testing.assert_frame_equal(errors, repeated_errors)


def test_comparison_rejects_relabel_missing_cell_and_reference_substitution(
    tmp_path: Path,
) -> None:
    holdout, reference = _comparison_fixture(tmp_path)
    predictions = _prediction_frames()
    predictions["weak_label_logistic"].loc[2, "split"] = "train"
    with pytest.raises(ControlledExperimentError, match="relabelled"):
        compare_three_model_predictions(
            predictions,
            holdout,
            reference_cells=reference,
            thresholds=_thresholds(),
        )

    predictions = _prediction_frames()
    predictions["geoai_candidate"] = predictions["geoai_candidate"].iloc[:-1]
    with pytest.raises(ControlledExperimentError, match="frozen membership"):
        compare_three_model_predictions(
            predictions,
            holdout,
            reference_cells=reference,
            thresholds=_thresholds(),
        )

    predictions = _prediction_frames()
    predictions["geoai_candidate"]["reference_flood_extent"] = [0, 1, 1, 0, 0, 1]
    with pytest.raises(ControlledExperimentError, match="columns do not match"):
        compare_three_model_predictions(
            predictions,
            holdout,
            reference_cells=reference,
            thresholds=_thresholds(),
        )


def test_zero_division_convention_is_finite_and_documented(tmp_path: Path) -> None:
    dry_reference = _reference_frame()
    dry_reference["reference_flood_extent"] = 0
    holdout, reference = _comparison_fixture(tmp_path, reference_frame=dry_reference)
    predictions = _prediction_frames()
    for frame in predictions.values():
        frame["probability_0_1"] = 0.0

    metrics, _calibration, _errors = compare_three_model_predictions(
        predictions,
        holdout,
        reference_cells=reference,
        thresholds=_thresholds(),
    )

    numeric = metrics.select_dtypes(include="number")
    assert numeric.map(math.isfinite).all().all()
    assert metrics["iou"].eq(0.0).all()
    assert metrics["precision"].eq(0.0).all()
    assert metrics["recall"].eq(0.0).all()
    assert metrics["area_error_ratio"].eq(0.0).all()
    assert ZERO_DIVISION_CONVENTION.startswith("finite:")


def test_signed_reference_cells_reject_substitution_wrong_key_and_lineage(
    tmp_path: Path,
) -> None:
    _manifest, artifacts, _authority, acquisition = _authorized_acquisition(
        tmp_path / "acquisition"
    )
    holdout, _geometry, _grid, _membership, _holdout_receipt = _holdout_fixture(
        tmp_path / "holdout", acquisition=acquisition
    )
    bundle = _reference_bundle_fixture(
        tmp_path / "reference",
        acquisition,
        holdout,
        artifacts["reference_mask"],
    )
    reference = bundle["reference"]
    evidence_path = bundle["evidence"]
    receipt_path = bundle["receipt"]

    assert len(reference.cells) == len(holdout.memberships)
    assert reference.reference_mask_sha256 == acquisition.reference_mask_sha256

    original = evidence_path.read_bytes()
    substituted = pd.read_csv(evidence_path)
    substituted.loc[substituted["cell_id"].eq("C3"), "reference_flood_extent"] = 1
    substituted.to_csv(evidence_path, index=False, lineterminator="\n")
    with pytest.raises(ControlledExperimentError, match="checksum was substituted"):
        load_signed_reference_cell_evidence(
            receipt_path,
            evidence_path,
            acquisition=acquisition,
            reviewer_qualification=bundle["reviewer"],
            holdout=holdout,
            calibration_reference_path=bundle["calibration_path"],
            error_strata_path=bundle["error_strata"],
            signing_keys=SIGNING_KEYS,
        )
    evidence_path.write_bytes(original)

    with pytest.raises(ControlledExperimentError, match="not trusted at runtime"):
        load_signed_reference_cell_evidence(
            receipt_path,
            evidence_path,
            acquisition=acquisition,
            reviewer_qualification=bundle["reviewer"],
            holdout=holdout,
            calibration_reference_path=bundle["calibration_path"],
            error_strata_path=bundle["error_strata"],
            signing_keys={"wrong-key": SIGNING_KEY},
        )

    altered_roles = tuple(
        (role, SHA_B if role == "reference_mask" else digest)
        for role, digest in acquisition.sha256_by_role
    )
    altered_acquisition = replace(acquisition, sha256_by_role=altered_roles)
    with pytest.raises(ControlledExperimentError, match="reference_mask_sha256"):
        load_signed_reference_cell_evidence(
            receipt_path,
            evidence_path,
            acquisition=altered_acquisition,
            reviewer_qualification=bundle["reviewer"],
            holdout=holdout,
            calibration_reference_path=bundle["calibration_path"],
            error_strata_path=bundle["error_strata"],
            signing_keys=SIGNING_KEYS,
        )


def test_gate_receipt_stays_blocked_without_signed_authority_human_or_models(
    tmp_path: Path,
) -> None:
    manifest, artifacts = _acquisition_fixture(tmp_path, base_ready=False)
    acquisition = assess_acquisition_manifest(manifest, artifact_paths=artifacts)
    receipt = build_gate_receipt(
        acquisition,
        generated_at_utc=datetime(2026, 7, 16, tzinfo=UTC),
    )

    assert receipt["gate_status"] == "blocked"
    assert receipt["processing_allowed"] is False
    assert receipt["experiment_executed"] is False
    assert receipt["official_warning"] is False
    assert "C:\\" not in json.dumps(receipt)
    assert any("reviewer_calibration" in item for item in receipt["blockers"])
    assert any("acquisition_authority" in item for item in receipt["blockers"])

    outputs = write_gate_report(
        receipt,
        manifest,
        json_output_path=tmp_path / "gate.json",
        markdown_output_path=tmp_path / "gate.md",
    )
    report = outputs["report"].read_text(encoding="utf-8")
    assert "No real training" in report
    assert "editable CSV claims are not authority" in report


def test_full_runner_verifies_signed_artifacts_runs_and_thresholds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _runner_fixture(tmp_path, monkeypatch)

    outputs = _run_fixture(fixture, tmp_path / "results")

    result = json.loads(outputs["receipt"].read_text(encoding="utf-8"))
    assert result["comparison_status"] == "completed_report_only"
    assert result["can_feed_decision_layer"] is False
    assert result["official_warning"] is False
    assert result["zero_division_convention"] == ZERO_DIVISION_CONVENTION
    assert result["reference_cell_receipt_file_sha256"] == _sha(
        fixture["reference_receipt"]
    )
    assert result["reference_cell_evidence_sha256"] == _sha(
        fixture["reference_evidence"]
    )
    assert len(result["models"]) == 3
    assert {row["model_contract_schema"] for row in result["models"]} == set(
        MODEL_CONTRACT_SCHEMAS.values()
    )
    assert all(row["model_contract_file_sha256"] for row in result["models"])
    assert all(row["model_contract_sha256"] for row in result["models"])
    assert {row["floodguard_commit"] for row in result["models"]} == {"d" * 40}
    assert result["training_partition_sha256"]
    assert result["calibration_partition_sha256"]
    assert result["final_holdout_partition_sha256"]
    assert all(
        row["threshold_selection_scope"] == "verified_calibration_projection_only"
        for row in result["models"]
    )
    assert result["artifact_schema"] == controlled.RESULT_RECEIPT_SCHEMA
    assert result["promotion_policy_manifest_sha256"]
    assert result["signing_key_id"] == RESULT_KEY_ID
    assert result["manifest_sha256"]
    assert result["signature"]
    controlled._verify_signed_payload(
        result,
        SIGNING_KEYS,
        "experiment result receipt",
    )
    controlled._verify_self_hash(
        result,
        "manifest_sha256",
        "experiment result receipt",
    )
    assert pd.read_csv(outputs["metrics"]).shape[0] == 3
    assert pd.read_csv(outputs["runtime"]).shape[0] == 3
    assert "Three-model probability calibration curves" in outputs[
        "calibration_curve"
    ].read_text(encoding="utf-8")
    assert all(row["runtime_profile"] for row in result["models"])


def test_full_runner_publishes_atomically_and_cleans_failed_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _runner_fixture(tmp_path / "fixture", monkeypatch)
    output = tmp_path / "results"
    renderer = controlled._calibration_curve_svg

    def fail_render(_calibration: pd.DataFrame) -> str:
        raise RuntimeError("injected render failure")

    monkeypatch.setattr(controlled, "_calibration_curve_svg", fail_render)
    with pytest.raises(RuntimeError, match="injected render failure"):
        _run_fixture(fixture, output)

    assert not output.exists()
    assert not list(tmp_path.glob(".results.staging-*"))

    monkeypatch.setattr(controlled, "_calibration_curve_svg", renderer)
    outputs = _run_fixture(fixture, output)
    assert output.is_dir()
    assert all(path.parent == output and path.is_file() for path in outputs.values())
    assert not list(tmp_path.glob(".results.staging-*"))


def test_result_signing_key_and_expiry_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _runner_fixture(tmp_path / "fixture", monkeypatch)

    with pytest.raises(ControlledExperimentError, match="not trusted at runtime"):
        _run_fixture(
            fixture,
            tmp_path / "untrusted-result",
            result_signing_key_id="untrusted-result-key",
        )

    with pytest.raises(ControlledExperimentError, match="expiry must be after"):
        _run_fixture(
            fixture,
            tmp_path / "expired-result",
            result_expires_at_utc=datetime(2024, 1, 5, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    ("crs", "nodata", "values", "message"),
    [
        ("EPSG:4326", 255, [0, 1, 0, 1, 0, 1], "CRS must exactly match"),
        ("EPSG:6933", 0, [0, 1, 0, 1, 0, 1], "nodata must be finite"),
        ("EPSG:6933", 255, [0, 1, 2, 1, 0, 1], "only binary classes"),
    ],
)
def test_reference_mask_derivation_rejects_crs_nodata_and_class_substitution(
    tmp_path: Path,
    crs: str,
    nodata: int,
    values: list[int],
    message: str,
) -> None:
    holdout, _geometry, _grid, _membership, _receipt = _holdout_fixture(
        tmp_path / "holdout"
    )
    mask_path = tmp_path / "reference-mask.tif"
    with rasterio.open(
        mask_path,
        "w",
        driver="GTiff",
        width=6,
        height=1,
        count=1,
        dtype="uint8",
        crs=crs,
        transform=Affine(50, 0, 0, 0, -50, 75),
        nodata=nodata,
    ) as dataset:
        dataset.write(pd.Series(values).to_numpy(dtype="uint8").reshape(1, 1, 6))
    strata = _reference_frame().loc[:, ["cell_id", *controlled.ERROR_STRATA]]

    with pytest.raises(ControlledExperimentError, match=message):
        controlled._derive_reference_cells_from_mask(
            mask_path,
            holdout=holdout,
            error_strata=strata,
            expected_sha256=_sha(mask_path),
        )


def test_threshold_calibration_projection_rejects_final_holdout_leakage(
    tmp_path: Path,
) -> None:
    _manifest, artifacts, _authority, acquisition = _authorized_acquisition(
        tmp_path / "acquisition"
    )
    holdout, _geometry, _grid, _membership, _receipt = _holdout_fixture(
        tmp_path / "holdout", acquisition=acquisition
    )
    bundle = _reference_bundle_fixture(
        tmp_path / "reference",
        acquisition,
        holdout,
        artifacts["reference_mask"],
    )
    prediction = (
        _prediction_frames()["geoai_candidate"]
        .loc[lambda frame: frame["split"].eq("calibration")]
        .reset_index(drop=True)
    )
    prediction.loc[1, ["cell_id", "spatial_group_id", "split"]] = [
        "C5",
        "FINAL-HOLDOUT-C",
        "final_holdout",
    ]

    with pytest.raises(
        ControlledExperimentError, match="does not exactly cover calibration cells"
    ):
        controlled_threshold._validated_calibration_prediction(
            prediction,
            family="geoai_candidate",
            holdout=holdout,
            calibration_reference=bundle["calibration"],
        )


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"training_seconds": -1.0}, "non-negative"),
        ({"total_seconds": 1.0}, "shorter than measured phases"),
        ({"peak_memory_mb": 0.0}, "must be positive"),
        ({"hardware_class": r"C:\\private\\machine"}, "private absolute path"),
        (
            {"hardware_class": "/workspace/floodguard/private-host"},
            "private absolute path",
        ),
        ({"hardware_class": "/usr/src/floodguard"}, "private absolute path"),
        ({"hardware_class": "/run/user/1000/floodguard"}, "private absolute path"),
    ],
)
def test_runtime_profile_rejects_unsafe_or_impossible_values(
    updates: dict[str, object],
    message: str,
) -> None:
    profile: dict[str, object] = {
        "training_seconds": 2.0,
        "calibration_seconds": 0.5,
        "inference_seconds": 1.0,
        "total_seconds": 3.5,
        "peak_memory_mb": 128.0,
        "device": "cpu",
        "hardware_class": "bounded-test-host",
    }
    profile.update(updates)

    with pytest.raises(ControlledExperimentError, match=message):
        controlled._validated_runtime_profile(profile)


def test_private_path_filter_allows_public_urls_and_api_routes() -> None:
    controlled._reject_private_paths(
        {
            "source_url": "https://example.test/public/artifact",
            "api_route": "/api/v1/status",
        }
    )


def test_full_runner_rejects_model_artifact_and_run_manifest_substitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _runner_fixture(tmp_path / "artifact", monkeypatch)
    family = "geoai_candidate"
    fixture["model_artifacts"][family].write_bytes(b"substituted artifact")
    evidence = pd.read_csv(fixture["model_evidence"])
    evidence.loc[evidence["model_family"].eq(family), "model_artifact_sha256"] = _sha(
        fixture["model_artifacts"][family]
    )
    evidence.to_csv(fixture["model_evidence"], index=False, lineterminator="\n")
    with pytest.raises(ControlledExperimentError, match="model artifact"):
        _run_fixture(fixture, tmp_path / "artifact-results")

    fixture = _runner_fixture(tmp_path / "run", monkeypatch)
    family = "weak_label_logistic"
    run_path = fixture["model_runs"][family]
    run = json.loads(run_path.read_text(encoding="utf-8"))
    run["decision_threshold"] = 0.99
    run_path.write_text(json.dumps(run), encoding="utf-8")
    evidence = pd.read_csv(fixture["model_evidence"])
    evidence.loc[evidence["model_family"].eq(family), "model_run_manifest_sha256"] = (
        _sha(run_path)
    )
    evidence.to_csv(fixture["model_evidence"], index=False, lineterminator="\n")
    with pytest.raises(ControlledExperimentError, match="HMAC signature is invalid"):
        _run_fixture(fixture, tmp_path / "run-results")


@pytest.mark.parametrize(
    "partition_field",
    [
        "training_partition_sha256",
        "calibration_partition_sha256",
        "final_holdout_partition_sha256",
    ],
)
def test_signed_model_run_rejects_partition_hash_substitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    partition_field: str,
) -> None:
    fixture = _runner_fixture(tmp_path / partition_field, monkeypatch)
    family = "weak_label_logistic"
    run_path = fixture["model_runs"][family]
    run = json.loads(run_path.read_text(encoding="utf-8"))
    unsigned = {
        key: value
        for key, value in run.items()
        if key not in {"manifest_sha256", "signature"}
    }
    unsigned[partition_field] = "e" * 64
    resealed = controlled._seal_signed_payload(
        unsigned,
        signing_key_id=MODEL_KEY_ID,
        signing_key=MODEL_KEY,
        self_hash_field="manifest_sha256",
    )
    run_path.write_text(json.dumps(resealed), encoding="utf-8")
    evidence = pd.read_csv(fixture["model_evidence"])
    evidence.loc[evidence["model_family"].eq(family), "model_run_manifest_sha256"] = (
        _sha(run_path)
    )
    evidence.to_csv(fixture["model_evidence"], index=False, lineterminator="\n")

    with pytest.raises(
        ControlledExperimentError,
        match=f"signed {partition_field} was substituted",
    ):
        _run_fixture(fixture, tmp_path / f"{partition_field}-results")


@pytest.mark.parametrize(
    ("family", "field_path", "value", "message"),
    [
        (
            "deterministic_sar_baseline",
            ("lane", "algorithm"),
            "neural_net",
            "algorithm",
        ),
        (
            "weak_label_logistic",
            ("lane", "preprocessing"),
            "global_fit",
            "preprocessing",
        ),
        ("geoai_candidate", ("lane", "architecture"), "transformer", "architecture"),
        ("geoai_candidate", ("lane", "encoder_weights"), "imagenet", "encoder_weights"),
        ("geoai_candidate", ("lane", "geoai_commit"), "0" * 40, "source commit"),
        (
            "geoai_candidate",
            ("lane", "preprocessing", "method"),
            "implicit_divide_255",
            "explicitly encode",
        ),
        ("geoai_candidate", ("floodguard_commit",), "short", "FloodGuard commit"),
    ],
)
def test_lane_contracts_reject_wrong_family_configuration(
    tmp_path: Path,
    family: str,
    field_path: tuple[str, ...],
    value: object,
    message: str,
) -> None:
    artifact = tmp_path / f"{family}.bin"
    artifact.write_bytes(b"model")
    model_id = "MODEL-TEST"
    contract_path = _model_lane_contract(tmp_path, family, model_id, artifact)
    payload = json.loads(contract_path.read_text(encoding="utf-8"))
    target = payload
    for field in field_path[:-1]:
        target = target[field]
    target[field_path[-1]] = value
    contract_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    with pytest.raises(ControlledExperimentError, match=message):
        controlled._load_model_lane_contract(
            contract_path,
            family=family,
            model_id=model_id,
            model_artifact_sha256=_sha(artifact),
        )


def test_full_runner_rejects_coordinated_lane_contract_substitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _runner_fixture(tmp_path, monkeypatch)
    family = "geoai_candidate"
    contract_path = fixture["model_contracts"][family]
    payload = json.loads(contract_path.read_text(encoding="utf-8"))
    payload["lane"]["architecture"] = "fpn"
    contract_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    evidence = pd.read_csv(fixture["model_evidence"])
    mask = evidence["model_family"].eq(family)
    evidence.loc[mask, "model_contract_file_sha256"] = _sha(contract_path)
    evidence.loc[mask, "model_contract_sha256"] = controlled._canonical_sha256(payload)
    evidence.to_csv(fixture["model_evidence"], index=False, lineterminator="\n")

    with pytest.raises(ControlledExperimentError, match="signed lane contract"):
        _run_fixture(fixture, tmp_path / "results")


def test_full_runner_rejects_coordinated_all_prediction_substitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _runner_fixture(tmp_path, monkeypatch)
    evidence = pd.read_csv(fixture["model_evidence"])
    for family, prediction_path in fixture["predictions"].items():
        prediction = pd.read_csv(prediction_path)
        prediction["probability_0_1"] = 0.99
        prediction.to_csv(prediction_path, index=False, lineterminator="\n")
        evidence.loc[evidence["model_family"].eq(family), "prediction_sha256"] = _sha(
            prediction_path
        )
    evidence.to_csv(fixture["model_evidence"], index=False, lineterminator="\n")

    with pytest.raises(
        ControlledExperimentError, match="signed prediction was substituted"
    ):
        _run_fixture(fixture, tmp_path / "results")


def test_signed_run_rejects_wrong_contract_and_editable_threshold_column(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _runner_fixture(tmp_path / "contract", monkeypatch)
    family = "deterministic_sar_baseline"
    run_path = fixture["model_runs"][family]
    run = json.loads(run_path.read_text(encoding="utf-8"))
    unsigned = {
        key: value
        for key, value in run.items()
        if key not in {"manifest_sha256", "signature"}
    }
    unsigned["model_contract_schema"] = "floodguard.wrong_contract.v1"
    resealed = controlled._seal_signed_payload(
        unsigned,
        signing_key_id=MODEL_KEY_ID,
        signing_key=MODEL_KEY,
        self_hash_field="manifest_sha256",
    )
    run_path.write_text(json.dumps(resealed), encoding="utf-8")
    evidence = pd.read_csv(fixture["model_evidence"])
    evidence.loc[evidence["model_family"].eq(family), "model_run_manifest_sha256"] = (
        _sha(run_path)
    )
    evidence.to_csv(fixture["model_evidence"], index=False, lineterminator="\n")
    with pytest.raises(ControlledExperimentError, match="contract schema mismatch"):
        _run_fixture(fixture, tmp_path / "contract-results")

    fixture = _runner_fixture(tmp_path / "editable", monkeypatch)
    evidence = pd.read_csv(fixture["model_evidence"])
    evidence["decision_threshold"] = 0.01
    evidence.to_csv(fixture["model_evidence"], index=False, lineterminator="\n")
    with pytest.raises(ControlledExperimentError, match="extra=.*decision_threshold"):
        _run_fixture(fixture, tmp_path / "editable-results")


def test_committed_blocked_report_and_no_root_geoai_import() -> None:
    root = Path(__file__).resolve().parents[1]
    receipt_path = root / "docs/validation/controlled_three_model_gate_receipt.json"
    manifest_path = root / "docs/validation/controlled_three_model_acquisition_manifest.csv"
    receipt = json.loads(
        receipt_path.read_text(encoding="utf-8")
    )
    manifest = pd.read_csv(manifest_path)
    assert receipt["acquisition"]["manifest_file_sha256"] == _sha(manifest_path)
    assert receipt["receipt_sha256"] == controlled._canonical_sha256(
        {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    )
    report = build_gate_report_markdown(receipt, manifest)
    assert receipt["gate_status"] == "blocked"
    assert "No real training" in report
    assert any("acquisition_authority" in item for item in receipt["blockers"])
    assert "import geoai" not in (
        root / "src/floodguard/controlled_experiment.py"
    ).read_text(encoding="utf-8")

    contradictory_receipt = json.loads(json.dumps(receipt))
    contradictory_receipt["processing_allowed"] = True
    contradictory_receipt["receipt_sha256"] = controlled._canonical_sha256(
        {
            key: value
            for key, value in contradictory_receipt.items()
            if key != "receipt_sha256"
        }
    )
    with pytest.raises(
        ControlledExperimentError, match="unsafe or contradictory status fields"
    ):
        build_gate_report_markdown(contradictory_receipt, manifest)


def _acquisition_fixture(
    tmp_path: Path,
    *,
    base_ready: bool,
    reference_values: list[int] | None = None,
) -> tuple[Path, dict[str, Path]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    contents = {
        "pre_event_sar": b"pre",
        "post_event_sar": b"post",
    }
    artifacts: dict[str, Path] = {}
    for role, content in contents.items():
        path = tmp_path / f"{role}.bin"
        path.write_bytes(content)
        artifacts[role] = path
    reference_path = tmp_path / "reference_mask.tif"
    values = reference_values or [0, 1, 0, 1, 0, 1]
    with rasterio.open(
        reference_path,
        "w",
        driver="GTiff",
        width=6,
        height=1,
        count=1,
        dtype="uint8",
        crs="EPSG:6933",
        transform=Affine(50.0, 0.0, 0.0, 0.0, -50.0, 75.0),
        nodata=255,
    ) as dataset:
        dataset.write(pd.DataFrame([values]).to_numpy(dtype="uint8"), 1)
    artifacts["reference_mask"] = reference_path
    times = {
        "pre_event_sar": ("2023-12-31T00:00:00Z", "2023-12-31T00:01:00Z"),
        "post_event_sar": ("2024-01-02T00:00:00Z", "2024-01-02T00:01:00Z"),
        "reference_mask": ("2024-01-02T00:00:00Z", "2024-01-02T23:59:59Z"),
    }
    rows = []
    for role in contents_roles():
        is_reference = role == "reference_mask"
        row_ready = base_ready or not is_reference
        start, end = times[role]
        rows.append(
            {
                "schema_version": ACQUISITION_SCHEMA,
                "experiment_id": "EXP-1",
                "study_area": "Test area",
                "role": role,
                "source_name": f"Source {role}",
                "source_url": f"https://example.test/{role}",
                "product_id": f"PRODUCT-{role}",
                "acquisition_start_utc": start,
                "acquisition_end_utc": end,
                "local_path_hint": (
                    f"<external_data_workspace>/{artifacts[role].name}"
                ),
                "sha256": _sha(artifacts[role]),
                "sha256_status": "verified",
                "license_status": (
                    "confirmed_for_experiment" if row_ready else "unresolved"
                ),
                "local_analysis_allowed": row_ready,
                "derived_metrics_allowed": row_ready,
                "ml_label_use_allowed": row_ready,
                "redistribution_status": (
                    "reference_only" if row_ready else "unresolved"
                ),
                "reference_mask_status": (
                    "qualified_expert_or_adjudicated"
                    if is_reference and row_ready
                    else "candidate_not_qualified"
                    if is_reference
                    else "not_applicable"
                ),
                "temporal_alignment_status": (
                    "confirmed" if row_ready else "unresolved"
                ),
                "processing_allowed": row_ready,
                "source_timestamp": end,
                "assumptions": "Synthetic test fixture.",
            }
        )
    manifest = tmp_path / "acquisition.csv"
    pd.DataFrame(rows, columns=ACQUISITION_COLUMNS).to_csv(
        manifest,
        index=False,
        lineterminator="\n",
    )
    return manifest, artifacts


def _issue_authority(
    tmp_path: Path,
    manifest: Path,
    base: controlled.AcquisitionGateAssessment,
) -> Path:
    frame = pd.read_csv(manifest).fillna("")
    catalog_paths: dict[str, Path] = {}
    license_paths: dict[str, Path] = {}
    for role in contents_roles():
        catalog_path = tmp_path / f"{role}-catalog.json"
        catalog_path.write_text(
            json.dumps({"role": role, "record": "test catalog"}),
            encoding="utf-8",
        )
        license_path = tmp_path / f"{role}-license.txt"
        license_path.write_text(
            f"Externally reviewed license evidence for {role}.",
            encoding="utf-8",
        )
        catalog_paths[role] = catalog_path
        license_paths[role] = license_path
    products: list[dict[str, object]] = []
    for raw in frame.sort_values("role").to_dict("records"):
        role = str(raw["role"])
        redistribution_status = str(raw["redistribution_status"])
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
                "catalog_evidence_sha256": _sha(catalog_paths[role]),
                "license_evidence_sha256": _sha(license_paths[role]),
                "terms_url": f"https://example.test/terms/{role}",
                "license_status": str(raw["license_status"]),
                "redistribution_status": redistribution_status,
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
                    "source_redistribution": (
                        redistribution_status == "redistributable"
                    ),
                    "derived_geometry_redistribution": True,
                    "reference_only_storage_if_not_redistributable": True,
                },
                "reference_qualification": (
                    {
                        "status": "qualified_expert_or_adjudicated",
                        "qualification_method": (
                            "Independent blind review with resolved adjudication."
                        ),
                        "known_uncertainty_and_error_categories": (
                            "Boundary ambiguity, permanent water, and radar shadow."
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
        "decision_id": "TEST-EXTERNAL-DECISION-1",
        "request_id": "TEST-EXTERNAL-REQUEST-1",
        "experiment_id": base.experiment_id,
        "study_area": base.study_area,
        "acquisition_manifest_sha256": base.manifest_sha256,
        "decision_status": "approved_for_controlled_experiment",
        "products": products,
        "required_attribution_and_conditions": {
            "unmodified_source_notice": "Retain source-provider attribution.",
            "modified_or_derived_notice": "Label all derived FloodGuard outputs.",
            "citation": "Synthetic authority fixture citation.",
            "disclaimer": "No operational or official-warning endorsement.",
            "additional_conditions": "Controlled experiment use only.",
        },
        "authorized_signer": {
            "name": "Test External Custodian",
            "organization": "Test Data Authority",
            "title_or_role": "Authorized data custodian",
            "authority_basis": "Delegated authority over the listed product records.",
            "identity_evidence_type": "verified authority registry record",
            "identity_evidence_sha256": "7" * 64,
            "decision_issued_at_utc": "2024-01-03T00:00:00Z",
            "decision_expires_at_utc": "2030-01-01T00:00:00Z",
            "signing_key_id": EXTERNAL_KEY_ID,
            "signature_algorithm": "Ed25519",
            "public_key_sha256": hashlib.sha256(EXTERNAL_PUBLIC_KEY).hexdigest(),
        },
        "signer_attestations": {
            field: True for field in controlled.EXTERNAL_SIGNER_ATTESTATIONS
        },
        "official_warning": False,
    }
    decision_path = tmp_path / "external-authority-decision.json"
    decision_path.write_text(
        json.dumps(decision, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    signature_path = tmp_path / "external-authority-decision.sig"
    signature_path.write_text(
        _ed25519_sign(EXTERNAL_SEED, controlled._canonical_json_bytes(decision)).hex()
        + "\n",
        encoding="ascii",
    )
    authority = tmp_path / "acquisition-authority.json"
    write_acquisition_authority_receipt(
        base,
        manifest,
        external_authority_decision_path=decision_path,
        external_authority_signature_path=signature_path,
        external_authority_public_keys=EXTERNAL_PUBLIC_KEYS,
        catalog_evidence_paths_by_role=catalog_paths,
        license_evidence_paths_by_role=license_paths,
        verified_at_utc=datetime(2024, 1, 5, tzinfo=UTC),
        receipt_signing_key_id=KEY_ID,
        receipt_signing_key=SIGNING_KEY,
        output_path=authority,
    )
    return authority


def _authorized_acquisition(
    tmp_path: Path,
    *,
    reference_values: list[int] | None = None,
) -> tuple[Path, dict[str, Path], Path, controlled.AcquisitionGateAssessment]:
    manifest, artifacts = _acquisition_fixture(
        tmp_path,
        base_ready=True,
        reference_values=reference_values,
    )
    base = assess_acquisition_manifest(manifest, artifact_paths=artifacts)
    authority = _issue_authority(tmp_path, manifest, base)
    assessment = assess_acquisition_manifest(
        manifest,
        artifact_paths=artifacts,
        authority_receipt_path=authority,
        signing_keys=SIGNING_KEYS,
        external_authority_public_keys=EXTERNAL_PUBLIC_KEYS,
        verified_at_utc=datetime(2024, 1, 5, tzinfo=UTC),
    )
    return manifest, artifacts, authority, assessment


def contents_roles() -> tuple[str, str, str]:
    return ("pre_event_sar", "post_event_sar", "reference_mask")


def _reviewer_release_lineage_fixture(
    tmp_path: Path,
) -> tuple[dict[str, object], SimpleNamespace, Path]:
    query_ids = tuple(f"CAL-{index:02d}" for index in range(12))
    membership = pd.DataFrame(
        {
            "query_region_id": query_ids,
            "min_x": [float(index) for index in range(12)],
            "min_y": [0.0] * 12,
            "max_x": [float(index + 1) for index in range(12)],
            "max_y": [1.0] * 12,
            "grid_contract_sha256": ["1" * 64] * 12,
            "source_registry_sha256": ["2" * 64] * 12,
            "source_timestamp": ["2024-01-02T00:00:00Z"] * 12,
        }
    )
    membership_path = tmp_path / controlled.CALIBRATION_QUERIES_NAME
    membership.to_csv(membership_path, index=False, lineterminator="\n")
    release: dict[str, object] = {
        "selection_contract": {
            "calibration_query_ids": list(query_ids),
            "fresh_retest_query_ids": [f"RETEST-{index:02d}" for index in range(12)],
        },
        "artifacts": [
            {
                "package_path": controlled.CALIBRATION_QUERIES_NAME,
                "sha256": _sha(membership_path),
            }
        ],
    }
    reviewer = SimpleNamespace(
        query_region_ids=query_ids,
        query_manifest_sha256=_sha(membership_path),
        grid_contract_sha256_by_query=tuple(
            (query_id, "1" * 64) for query_id in query_ids
        ),
        source_registry_sha256_by_query=tuple(
            (query_id, "2" * 64) for query_id in query_ids
        ),
        source_timestamp_by_query=tuple(
            (query_id, "2024-01-02T00:00:00Z") for query_id in query_ids
        ),
    )
    return release, reviewer, membership_path


def test_reviewer_qualification_binds_exact_release_query_geometry(
    tmp_path: Path,
) -> None:
    release, reviewer, membership_path = _reviewer_release_lineage_fixture(tmp_path)
    lineage = controlled._validate_reviewer_calibration_release_lineage(
        release_package_path=tmp_path,
        release=release,
        reviewer=reviewer,
        calibration_attempt="initial",
    )
    assert lineage["approved_query_manifest_file_sha256"] == _sha(membership_path)

    substituted = pd.read_csv(membership_path)
    substituted.loc[0, "min_x"] = 999.0
    substituted_path = tmp_path / "same-ids-substituted-geometry.csv"
    substituted.to_csv(substituted_path, index=False, lineterminator="\n")
    reviewer.query_manifest_sha256 = _sha(substituted_path)
    with pytest.raises(
        ControlledExperimentError, match="exact frozen release artifact"
    ):
        controlled._validate_reviewer_calibration_release_lineage(
            release_package_path=tmp_path,
            release=release,
            reviewer=reviewer,
            calibration_attempt="initial",
        )


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("grid_contract_sha256_by_query", "3" * 64, "grid lineage"),
        ("source_registry_sha256_by_query", "4" * 64, "source-registry lineage"),
        (
            "source_timestamp_by_query",
            "2024-01-03T00:00:00Z",
            "source timestamps",
        ),
    ],
)
def test_reviewer_qualification_rejects_same_id_lineage_substitution(
    tmp_path: Path,
    field: str,
    replacement: str,
    message: str,
) -> None:
    release, reviewer, _membership_path = _reviewer_release_lineage_fixture(tmp_path)
    values = list(getattr(reviewer, field))
    values[0] = (values[0][0], replacement)
    setattr(reviewer, field, tuple(values))

    with pytest.raises(ControlledExperimentError, match=message):
        controlled._validate_reviewer_calibration_release_lineage(
            release_package_path=tmp_path,
            release=release,
            reviewer=reviewer,
            calibration_attempt="initial",
        )


def _adjudication_payload(
    acquisition: controlled.AcquisitionGateAssessment,
) -> dict[str, object]:
    return {
        "artifact_schema": "floodguard.controlled_adjudication_evidence.v3",
        "experiment_id": acquisition.experiment_id,
        "study_area": acquisition.study_area,
        "calibration_release_id": "release-1",
        "reference_mask_sha256": acquisition.reference_mask_sha256,
        "reviewer_ids": ["REVIEWER-A", "REVIEWER-B"],
        "reviewer_cell_sha256_by_reviewer": {
            "REVIEWER-A": "a" * 64,
            "REVIEWER-B": "b" * 64,
        },
        "adjudicator_id": "ADJUDICATOR-C",
        "formal_review_started_at_utc": "2026-07-20T03:00:01Z",
        "completed_at_utc": "2026-07-20T03:05:00Z",
        "disagreement_count": 2,
        "resolved_disagreement_count": 2,
        "unresolved_disagreement_count": 0,
        "disagreement_resolutions": [
            {
                "disagreement_id": "DISAGREEMENT-001",
                "query_region_id": "QUERY-001",
                "reviewer_decision_sha256_by_reviewer": {
                    "REVIEWER-A": "1" * 64,
                    "REVIEWER-B": "2" * 64,
                },
                "adjudication_outcome": "accept_a",
                "resolution_reason": "Independent source evidence supports flood.",
            },
            {
                "disagreement_id": "DISAGREEMENT-002",
                "query_region_id": "QUERY-002",
                "reviewer_decision_sha256_by_reviewer": {
                    "REVIEWER-A": "3" * 64,
                    "REVIEWER-B": "4" * 64,
                },
                "adjudication_outcome": "redraw",
                "resolution_reason": "Boundary ambiguity was resolved conservatively.",
            },
        ],
        "resolution_method": "Independent adjudicator review with recorded reasons.",
        "assumptions": "Synthetic contract fixture only.",
    }


def test_reviewer_decision_lineage_reopens_exact_cells_and_finds_disagreements(
    tmp_path: Path,
) -> None:
    paths: dict[str, Path] = {}
    rows = {
        "REVIEWER-A": [
            {
                "reviewer_id": "REVIEWER-A",
                "query_region_id": "QUERY-001",
                "cell_id": "C1",
                "label_code": 1,
            },
            {
                "reviewer_id": "REVIEWER-A",
                "query_region_id": "QUERY-002",
                "cell_id": "C2",
                "label_code": 0,
            },
        ],
        "REVIEWER-B": [
            {
                "reviewer_id": "REVIEWER-B",
                "query_region_id": "QUERY-001",
                "cell_id": "C1",
                "label_code": 0,
            },
            {
                "reviewer_id": "REVIEWER-B",
                "query_region_id": "QUERY-002",
                "cell_id": "C2",
                "label_code": 0,
            },
        ],
    }
    for reviewer_id, reviewer_rows in rows.items():
        path = tmp_path / f"{reviewer_id.lower()}-cells.csv"
        pd.DataFrame(reviewer_rows).to_csv(path, index=False, lineterminator="\n")
        paths[reviewer_id] = path
    reviewer = SimpleNamespace(
        reviewer_ids=("REVIEWER-A", "REVIEWER-B"),
        reviewer_cell_sha256_by_reviewer=tuple(
            sorted((reviewer_id, _sha(path)) for reviewer_id, path in paths.items())
        ),
    )

    lineage = controlled._reviewer_cell_decision_lineage(
        paths,
        reviewer=reviewer,
        expected_query_ids=("QUERY-001", "QUERY-002"),
    )

    assert lineage["disagreement_query_ids"] == ("QUERY-001",)
    assert set(lineage["reviewer_decision_sha256_by_query"]) == {
        "QUERY-001",
        "QUERY-002",
    }
    assert lineage["reviewer_cell_files_by_reviewer"] == {
        reviewer_id: path.name for reviewer_id, path in paths.items()
    }

    substituted = pd.read_csv(paths["REVIEWER-A"])
    substituted.loc[0, "label_code"] = 2
    substituted.to_csv(paths["REVIEWER-A"], index=False, lineterminator="\n")
    with pytest.raises(ControlledExperimentError, match="checksum differs"):
        controlled._reviewer_cell_decision_lineage(
            paths,
            reviewer=reviewer,
            expected_query_ids=("QUERY-001", "QUERY-002"),
        )


def test_reviewer_qualification_writer_binds_exact_cell_disagreements(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _manifest, _artifacts, _authority, acquisition = _authorized_acquisition(
        tmp_path / "acquisition"
    )
    package = tmp_path / "release"
    package.mkdir()
    release_receipt_path = package / "calibration_release_receipt.json"
    release_receipt_path.write_text("{}\n", encoding="utf-8")
    calibration_ids = tuple(f"CAL-{index:02d}" for index in range(12))
    retest_ids = tuple(f"RETEST-{index:02d}" for index in range(12))
    membership = pd.DataFrame(
        {
            "query_region_id": calibration_ids,
            "grid_contract_sha256": ["1" * 64] * 12,
            "source_registry_sha256": ["2" * 64] * 12,
            "source_timestamp": ["2024-01-02T00:00:00Z"] * 12,
        }
    )
    membership_path = package / controlled.CALIBRATION_QUERIES_NAME
    membership.to_csv(membership_path, index=False, lineterminator="\n")
    release = {
        "release_id": "release-1",
        "event_id": "EVENT-1",
        "receipt_sha256": "3" * 64,
        "authority_approval": {"manifest_sha256": "4" * 64},
        "selection_contract": {
            "calibration_query_ids": list(calibration_ids),
            "fresh_retest_query_ids": list(retest_ids),
        },
        "artifacts": [
            {
                "package_path": controlled.CALIBRATION_QUERIES_NAME,
                "sha256": _sha(membership_path),
            }
        ],
    }
    reviewer_paths: dict[str, Path] = {}
    for reviewer_id in ("REVIEWER-A", "REVIEWER-B"):
        rows = []
        for index, query_id in enumerate(calibration_ids):
            label = 1 if reviewer_id == "REVIEWER-A" and index == 0 else 0
            rows.append(
                {
                    "reviewer_id": reviewer_id,
                    "query_region_id": query_id,
                    "cell_id": f"{query_id}-C0000",
                    "label_code": label,
                }
            )
        path = tmp_path / f"{reviewer_id.lower()}-cells.csv"
        pd.DataFrame(rows).to_csv(path, index=False, lineterminator="\n")
        reviewer_paths[reviewer_id] = path
    reviewer = SimpleNamespace(
        reviewer_ids=("REVIEWER-A", "REVIEWER-B"),
        reviewer_cell_sha256_by_reviewer=tuple(
            sorted(
                (reviewer_id, _sha(path))
                for reviewer_id, path in reviewer_paths.items()
            )
        ),
        query_region_ids=calibration_ids,
        query_manifest_sha256=_sha(membership_path),
        grid_contract_sha256_by_query=tuple(
            (query_id, "1" * 64) for query_id in calibration_ids
        ),
        source_registry_sha256_by_query=tuple(
            (query_id, "2" * 64) for query_id in calibration_ids
        ),
        source_timestamp_by_query=tuple(
            (query_id, "2024-01-02T00:00:00Z") for query_id in calibration_ids
        ),
        formal_review_not_before_utc=datetime(2024, 1, 4, 1, tzinfo=UTC),
        calibration_completed_at_utc=datetime(2024, 1, 4, tzinfo=UTC),
        receipt_sha256="5" * 64,
        protocol_version="label_factory_protocol_v1",
        taxonomy_version="flood_label_v1",
    )
    monkeypatch.setattr(
        controlled,
        "validate_calibration_release_package",
        lambda _path: release,
    )
    monkeypatch.setattr(
        controlled,
        "_load_reviewer_calibration_snapshot",
        lambda _path: (reviewer, "6" * 64),
    )
    decision_lineage = controlled._reviewer_cell_decision_lineage(
        reviewer_paths,
        reviewer=reviewer,
        expected_query_ids=calibration_ids,
    )
    disagreement_id = decision_lineage["disagreement_query_ids"][0]
    adjudication = {
        "artifact_schema": "floodguard.controlled_adjudication_evidence.v3",
        "experiment_id": acquisition.experiment_id,
        "study_area": acquisition.study_area,
        "calibration_release_id": "release-1",
        "reference_mask_sha256": acquisition.reference_mask_sha256,
        "reviewer_ids": ["REVIEWER-A", "REVIEWER-B"],
        "reviewer_cell_sha256_by_reviewer": decision_lineage[
            "reviewer_cell_sha256_by_reviewer"
        ],
        "adjudicator_id": "ADJUDICATOR-C",
        "formal_review_started_at_utc": "2024-01-04T02:00:00Z",
        "completed_at_utc": "2024-01-04T03:00:00Z",
        "disagreement_count": 1,
        "resolved_disagreement_count": 1,
        "unresolved_disagreement_count": 0,
        "disagreement_resolutions": [
            {
                "disagreement_id": "DISAGREEMENT-001",
                "query_region_id": disagreement_id,
                "reviewer_decision_sha256_by_reviewer": decision_lineage[
                    "reviewer_decision_sha256_by_query"
                ][disagreement_id],
                "adjudication_outcome": "accept_a",
                "resolution_reason": "Independent adjudicator accepted reviewer A.",
            }
        ],
        "resolution_method": "Independent adjudication of exact cell evidence.",
        "assumptions": "Synthetic contract fixture only.",
    }
    adjudication_path = tmp_path / "adjudication.json"
    adjudication_path.write_text(json.dumps(adjudication), encoding="utf-8")
    error_strata_path = tmp_path / "error-strata.csv"
    pd.DataFrame(
        [
            {
                "cell_id": "CAL-00-C0000",
                **{category: False for category in controlled.ERROR_STRATA},
            }
        ]
    ).to_csv(error_strata_path, index=False, lineterminator="\n")
    reviewer_receipt_path = tmp_path / "reviewer-calibration.json"
    reviewer_receipt_path.write_text("{}\n", encoding="utf-8")
    output = tmp_path / "reviewer-qualification.json"

    receipt = controlled.write_signed_reviewer_qualification_receipt(
        acquisition=acquisition,
        calibration_release_package_path=package,
        reviewer_calibration_receipt_path=reviewer_receipt_path,
        reviewer_cell_paths_by_reviewer=reviewer_paths,
        calibration_attempt="initial",
        adjudication_evidence_path=adjudication_path,
        error_strata_path=error_strata_path,
        qualified_at_utc=datetime(2024, 1, 5, tzinfo=UTC),
        expires_at_utc=datetime(2030, 1, 1, tzinfo=UTC),
        reviewer_signing_key_id=REVIEWER_KEY_ID,
        reviewer_signing_key=REVIEWER_KEY,
        adjudicator_signing_key_id=ADJUDICATOR_KEY_ID,
        adjudicator_signing_key=ADJUDICATOR_KEY,
        output_path=output,
    )

    assert receipt["artifact_schema"].endswith(".v3")
    assert (
        receipt["reviewer_cell_sha256_by_reviewer"]
        == decision_lineage["reviewer_cell_sha256_by_reviewer"]
    )
    assert receipt["reviewer_decision_manifest_sha256"] == (
        controlled._canonical_sha256(
            decision_lineage["reviewer_decision_sha256_by_query"]
        )
    )


def _validate_adjudication_fixture(
    acquisition: controlled.AcquisitionGateAssessment,
    payload: dict[str, object],
) -> None:
    controlled._validate_adjudication_evidence(
        payload,
        acquisition=acquisition,
        reviewer_ids=("REVIEWER-A", "REVIEWER-B"),
        calibration_release_id="release-1",
        reviewer_not_before=datetime(2026, 7, 20, 2, tzinfo=UTC),
        reviewer_completed_at=datetime(2026, 7, 20, 3, tzinfo=UTC),
        expected_query_ids=("QUERY-001", "QUERY-002"),
        expected_reviewer_cell_sha256_by_reviewer={
            "REVIEWER-A": "a" * 64,
            "REVIEWER-B": "b" * 64,
        },
        expected_reviewer_decision_sha256_by_query={
            "QUERY-001": {"REVIEWER-A": "1" * 64, "REVIEWER-B": "2" * 64},
            "QUERY-002": {"REVIEWER-A": "3" * 64, "REVIEWER-B": "4" * 64},
        },
        expected_disagreement_query_ids=("QUERY-001", "QUERY-002"),
    )


def test_adjudication_requires_traceable_post_review_resolutions(
    tmp_path: Path,
) -> None:
    _manifest, _artifacts, _authority, acquisition = _authorized_acquisition(tmp_path)
    _validate_adjudication_fixture(acquisition, _adjudication_payload(acquisition))


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda value: value.__setitem__(
                "formal_review_started_at_utc", "2026-07-20T02:59:59Z"
            ),
            "chronology",
        ),
        (
            lambda value: value["disagreement_resolutions"].pop(),
            "do not match disagreement_count",
        ),
        (
            lambda value: value["disagreement_resolutions"][1].__setitem__(
                "disagreement_id", "DISAGREEMENT-001"
            ),
            "IDs must be unique",
        ),
        (
            lambda value: value["disagreement_resolutions"][0].__setitem__(
                "query_region_id", "UNAPPROVED-QUERY"
            ),
            "without an exact reviewer-cell disagreement",
        ),
        (
            lambda value: value["disagreement_resolutions"][0].__setitem__(
                "reviewer_decision_sha256_by_reviewer",
                {"REVIEWER-A": "1" * 64, "REVIEWER-B": "1" * 64},
            ),
            "differ from exact reviewer cells",
        ),
        (
            lambda value: value["disagreement_resolutions"][0].__setitem__(
                "adjudication_outcome", "kiwi"
            ),
            "outside the approved taxonomy",
        ),
    ],
)
def test_adjudication_substitution_fails_closed(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    _manifest, _artifacts, _authority, acquisition = _authorized_acquisition(tmp_path)
    payload = _adjudication_payload(acquisition)
    mutate(payload)
    with pytest.raises(ControlledExperimentError, match=message):
        _validate_adjudication_fixture(acquisition, payload)


def _holdout_geojson(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    payload = {
        "type": "FeatureCollection",
        "floodguard_crs": "EPSG:6933",
        "features": [
            {
                "type": "Feature",
                "properties": {"spatial_group_id": "TRAIN-A", "split": "train"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]]],
                },
            },
            {
                "type": "Feature",
                "properties": {
                    "spatial_group_id": "CALIBRATION-B",
                    "split": "calibration",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[100, 0], [200, 0], [200, 100], [100, 100], [100, 0]]
                    ],
                },
            },
            {
                "type": "Feature",
                "properties": {
                    "spatial_group_id": "FINAL-HOLDOUT-C",
                    "split": "final_holdout",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[200, 0], [300, 0], [300, 100], [200, 100], [200, 0]]
                    ],
                },
            },
        ],
    }
    path = tmp_path / "holdout.geojson"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _cell_grid(tmp_path: Path, *, outside: bool = False) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    contract = _grid_contract(tmp_path)
    x_values = [25.0, 75.0, 125.0, 175.0, 225.0, 350.0 if outside else 275.0]
    frame = pd.DataFrame(
        {
            "cell_id": ["C1", "C2", "C3", "C4", "C5", "C6"],
            "x": x_values,
            "y": [50.0] * 6,
            "row_index": [0] * 6,
            "column_index": [0, 1, 2, 3, 4, 5],
            "cell_area_m2": [2500.0] * 6,
            "grid_contract_sha256": [_sha(contract)] * 6,
        },
        columns=CELL_GRID_COLUMNS,
    )
    path = tmp_path / "cells.csv"
    frame.to_csv(path, index=False, lineterminator="\n")
    return path


def _grid_contract(tmp_path: Path) -> Path:
    path = tmp_path / "grid-contract.json"
    if path.exists():
        return path
    payload = {
        "artifact_schema": controlled.GRID_CONTRACT_SCHEMA,
        "grid_id": "TEST-GRID-1",
        "target_crs": "EPSG:6933",
        "transform": [50.0, 0.0, 0.0, 0.0, -50.0, 75.0],
        "width": 6,
        "height": 1,
        "cell_ids_sha256": controlled._canonical_sha256(
            ["C1", "C2", "C3", "C4", "C5", "C6"]
        ),
        "source_grid_sha256": hashlib.sha256(b"synthetic-grid-source").hexdigest(),
        "created_at_utc": "2023-12-31T00:00:00Z",
        "official_warning": False,
    }
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _freeze_paths(
    tmp_path: Path,
    geometry: Path,
    grid: Path,
    *,
    acquisition: controlled.AcquisitionGateAssessment | None = None,
) -> VerifiedSpatialHoldout:
    if acquisition is None:
        _manifest, _artifacts, _authority, acquisition = _authorized_acquisition(
            tmp_path / "acquisition"
        )
    return freeze_spatial_holdout(
        geometry,
        acquisition=acquisition,
        grid_contract_path=grid.with_name("grid-contract.json"),
        cell_grid_path=grid,
        membership_output_path=tmp_path / "membership.csv",
        target_crs="EPSG:6933",
        grid_contract_sha256=_sha(grid.with_name("grid-contract.json")),
        frozen_at_utc=datetime(2024, 1, 4, tzinfo=UTC),
        assumptions="Synthetic contract fixture.",
        signing_key_id=HOLDOUT_KEY_ID,
        signing_key=HOLDOUT_KEY,
        output_path=tmp_path / "holdout-receipt.json",
    )


def _holdout_fixture(
    tmp_path: Path,
    *,
    acquisition: controlled.AcquisitionGateAssessment | None = None,
) -> tuple[VerifiedSpatialHoldout, Path, Path, Path, Path]:
    geometry = _holdout_geojson(tmp_path)
    grid = _cell_grid(tmp_path)
    holdout = _freeze_paths(tmp_path, geometry, grid, acquisition=acquisition)
    return (
        holdout,
        geometry,
        tmp_path / "grid-contract.json",
        tmp_path / "membership.csv",
        tmp_path / "holdout-receipt.json",
    )


def _prediction_frames() -> dict[str, pd.DataFrame]:
    evidence = {
        "cell_id": ["C1", "C2", "C3", "C4", "C5", "C6"],
        "spatial_group_id": [
            "TRAIN-A",
            "TRAIN-A",
            "CALIBRATION-B",
            "CALIBRATION-B",
            "FINAL-HOLDOUT-C",
            "FINAL-HOLDOUT-C",
        ],
        "split": [
            "train",
            "train",
            "calibration",
            "calibration",
            "final_holdout",
            "final_holdout",
        ],
    }
    probabilities = {
        "deterministic_sar_baseline": [0.1, 0.8, 0.3, 0.7, 0.7, 0.6],
        "weak_label_logistic": [0.2, 0.7, 0.4, 0.8, 0.4, 0.8],
        "geoai_candidate": [0.1, 0.9, 0.2, 0.9, 0.2, 0.9],
    }
    return {
        family: pd.DataFrame({**evidence, "probability_0_1": values})
        for family, values in probabilities.items()
    }


def _reference_frame() -> pd.DataFrame:
    strata = {
        category: [False, False, False, False, False, False]
        for category in controlled.ERROR_STRATA
    }
    strata["permanent_water"] = [False, False, True, False, True, False]
    strata["radar_shadow"] = [False, True, False, False, False, False]
    strata["steep_terrain"] = [False, True, False, False, False, False]
    strata["urban_surface"] = [True, False, True, False, True, False]
    return pd.DataFrame(
        {
            "cell_id": ["C1", "C2", "C3", "C4", "C5", "C6"],
            "reference_flood_extent": [0, 1, 0, 1, 0, 1],
            **strata,
        },
        columns=controlled.REFERENCE_CELL_COLUMNS,
    )


def _reference_fixture(
    tmp_path: Path,
    acquisition: controlled.AcquisitionGateAssessment,
    holdout: VerifiedSpatialHoldout,
    reference_mask_path: Path,
    *,
    frame: pd.DataFrame | None = None,
) -> tuple[controlled.VerifiedReferenceCellEvidence, Path, Path]:
    bundle = _reference_bundle_fixture(
        tmp_path,
        acquisition,
        holdout,
        reference_mask_path,
        frame=frame,
    )
    return bundle["reference"], bundle["evidence"], bundle["receipt"]


def _reference_bundle_fixture(
    tmp_path: Path,
    acquisition: controlled.AcquisitionGateAssessment,
    holdout: VerifiedSpatialHoldout,
    reference_mask_path: Path,
    *,
    frame: pd.DataFrame | None = None,
) -> dict[str, object]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    reference_frame = frame if frame is not None else _reference_frame()
    error_strata_path = tmp_path / "error-strata.csv"
    reference_frame.loc[:, ["cell_id", *controlled.ERROR_STRATA]].to_csv(
        error_strata_path,
        index=False,
        lineterminator="\n",
    )
    reviewer_receipt_path = tmp_path / "reviewer-qualification.json"
    reviewer_payload: dict[str, object] = {
        "artifact_schema": controlled.REVIEWER_QUALIFICATION_SCHEMA,
        "experiment_id": acquisition.experiment_id,
        "study_area": acquisition.study_area,
        "acquisition_manifest_sha256": acquisition.manifest_sha256,
        "acquisition_authority_receipt_sha256": acquisition.authority_receipt_sha256,
        "acquisition_authority_signing_key_id": acquisition.authority_signing_key_id,
        "reference_mask_sha256": acquisition.reference_mask_sha256,
        "event_id": "TEST-EVENT-1",
        "calibration_release_id": "TEST-CALIBRATION-RELEASE-1",
        "calibration_release_receipt_sha256": "1" * 64,
        "calibration_release_file": "calibration_release_receipt.json",
        "calibration_release_file_sha256": "2" * 64,
        "reference_authority_approval_manifest_sha256": "3" * 64,
        "calibration_attempt": "initial",
        "calibration_query_ids": [f"CAL-{index:02d}" for index in range(12)],
        "fresh_retest_query_ids": [f"RETEST-{index:02d}" for index in range(12)],
        "approved_query_manifest_file": "calibration_queries.csv",
        "approved_query_manifest_file_sha256": "8" * 64,
        "reviewer_query_manifest_sha256": "8" * 64,
        "grid_contract_sha256_by_query": {
            f"CAL-{index:02d}": "9" * 64 for index in range(12)
        },
        "source_registry_sha256_by_query": {
            f"CAL-{index:02d}": "a" * 64 for index in range(12)
        },
        "source_timestamp_by_query": {
            f"CAL-{index:02d}": "2024-01-02T00:00:00Z" for index in range(12)
        },
        "reviewer_calibration_file": "reviewer-calibration.json",
        "reviewer_calibration_file_sha256": "4" * 64,
        "reviewer_calibration_receipt_sha256": "5" * 64,
        "reviewer_ids": ["REVIEWER-A", "REVIEWER-B"],
        "reviewer_cell_files_by_reviewer": {
            "REVIEWER-A": "reviewer-a-cells.csv",
            "REVIEWER-B": "reviewer-b-cells.csv",
        },
        "reviewer_cell_sha256_by_reviewer": {
            "REVIEWER-A": "a" * 64,
            "REVIEWER-B": "b" * 64,
        },
        "reviewer_decision_manifest_sha256": "c" * 64,
        "protocol_version": "test-protocol-v1",
        "taxonomy_version": "test-taxonomy-v1",
        "formal_review_not_before_utc": "2024-01-02T00:00:00Z",
        "adjudicator_id": "ADJUDICATOR-C",
        "adjudication_evidence_file": "adjudication.json",
        "adjudication_evidence_sha256": "6" * 64,
        "adjudication_resolution_manifest_sha256": "7" * 64,
        "disagreement_count": 2,
        "resolved_disagreement_count": 2,
        "unresolved_disagreement_count": 0,
        "error_strata_file": error_strata_path.name,
        "error_strata_file_sha256": _sha(error_strata_path),
        "qualified_at_utc": "2024-01-03T00:00:00Z",
        "expires_at_utc": "2030-01-01T00:00:00Z",
        "signing_roles": [
            controlled.SIGNING_ROLES["reviewer"],
            controlled.SIGNING_ROLES["adjudicator"],
        ],
        "qualification_status": "qualified_for_controlled_reference_derivation",
        "processing_allowed": True,
        "can_feed_decision_layer": False,
        "official_warning": False,
    }
    reviewer_receipt = controlled._seal_dual_signed_payload(
        reviewer_payload,
        reviewer_signing_key_id=REVIEWER_KEY_ID,
        reviewer_signing_key=REVIEWER_KEY,
        adjudicator_signing_key_id=ADJUDICATOR_KEY_ID,
        adjudicator_signing_key=ADJUDICATOR_KEY,
    )
    reviewer_receipt_path.write_text(
        json.dumps(reviewer_receipt, sort_keys=True),
        encoding="utf-8",
    )
    reviewer = controlled.load_signed_reviewer_qualification_receipt(
        reviewer_receipt_path,
        acquisition=acquisition,
        signing_keys=SIGNING_KEYS,
        verified_at_utc=datetime(2026, 7, 20, tzinfo=UTC),
    )
    evidence_path = tmp_path / "reference-cells.csv"
    calibration_path = tmp_path / "calibration-reference.csv"
    receipt_path = tmp_path / "reference-cells-receipt.json"
    write_signed_reference_cell_receipt(
        reference_mask_path,
        acquisition=acquisition,
        reviewer_qualification=reviewer,
        holdout=holdout,
        error_strata_path=error_strata_path,
        reference_cell_output_path=evidence_path,
        calibration_reference_output_path=calibration_path,
        derived_at_utc=datetime(2024, 1, 4, tzinfo=UTC),
        derivation_method="Synthetic qualified-mask fixture.",
        assumptions="Synthetic signed reference fixture.",
        signing_key_id=REFERENCE_KEY_ID,
        signing_key=REFERENCE_KEY,
        output_path=receipt_path,
    )
    verified = load_signed_reference_cell_evidence(
        receipt_path,
        evidence_path,
        acquisition=acquisition,
        reviewer_qualification=reviewer,
        holdout=holdout,
        calibration_reference_path=calibration_path,
        error_strata_path=error_strata_path,
        signing_keys=SIGNING_KEYS,
    )
    calibration = controlled.load_signed_calibration_reference_evidence(
        receipt_path,
        calibration_path,
        acquisition=acquisition,
        reviewer_qualification=reviewer,
        holdout=holdout,
        signing_keys=SIGNING_KEYS,
    )
    return {
        "reference": verified,
        "evidence": evidence_path,
        "receipt": receipt_path,
        "calibration": calibration,
        "calibration_path": calibration_path,
        "error_strata": error_strata_path,
        "reviewer": reviewer,
        "reviewer_receipt": reviewer_receipt_path,
    }


def _comparison_fixture(
    tmp_path: Path,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> tuple[VerifiedSpatialHoldout, controlled.VerifiedReferenceCellEvidence]:
    values = (
        reference_frame["reference_flood_extent"].astype(int).tolist()
        if reference_frame is not None
        else None
    )
    _manifest, artifacts, _authority, acquisition = _authorized_acquisition(
        tmp_path / "acquisition",
        reference_values=values,
    )
    holdout, _geometry, _grid, _membership, _receipt = _holdout_fixture(
        tmp_path / "holdout", acquisition=acquisition
    )
    reference, _evidence, _reference_receipt = _reference_fixture(
        tmp_path / "reference",
        acquisition,
        holdout,
        artifacts["reference_mask"],
        frame=reference_frame,
    )
    return holdout, reference


def _thresholds() -> dict[str, float]:
    return {family: 0.5 for family in REQUIRED_MODEL_FAMILIES}


def _model_lane_contract(
    tmp_path: Path,
    family: str,
    model_id: str,
    artifact: Path,
    *,
    execution_authorization_manifest_sha256: str = SHA_A,
    configuration_frozen_at_utc: str = "2024-01-03T00:00:00Z",
) -> Path:
    common: dict[str, object] = {
        "artifact_schema": MODEL_CONTRACT_SCHEMAS[family],
        "model_family": family,
        "model_id": model_id,
        "model_artifact_sha256": _sha(artifact),
        "floodguard_commit": "d" * 40,
        "prediction_semantics": "binary_flood_probability_class_1",
        "execution_authorization_manifest_sha256": (
            execution_authorization_manifest_sha256
        ),
        "configuration_frozen_at_utc": configuration_frozen_at_utc,
    }
    if family == "deterministic_sar_baseline":
        lane: dict[str, object] = {
            "algorithm": "deterministic_sar_change_baseline",
            "feature_names": list(controlled.REQUIRED_SAR_CHANNELS),
            "configuration_sha256": hashlib.sha256(b"sar-config").hexdigest(),
            "split_policy": "immutable_spatial_holdout",
        }
    elif family == "weak_label_logistic":
        lane = {
            "algorithm": "logistic_regression",
            "feature_names": ["vv_change", "vh_change", "slope"],
            "preprocessing": "training_fold_only_standardization",
            "configuration_sha256": hashlib.sha256(b"logistic-config").hexdigest(),
            "split_policy": "grouped_spatial",
        }
    else:
        lane = {
            "geoai_version": controlled.EXPECTED_GEOAI_VERSION,
            "geoai_commit": controlled.EXPECTED_GEOAI_COMMIT,
            "architecture": "unet",
            "encoder": "resnet34",
            "encoder_weights": None,
            "channel_names": [
                *controlled.REQUIRED_SAR_CHANNELS,
                "slope",
                "permanent_water",
            ],
            "preprocessing": {
                "method": "fixed_clip_scale_to_uint8",
                "value_domain": "uint8_0_255",
                "sidecar_sha256": hashlib.sha256(b"preprocess-sidecar").hexdigest(),
            },
            "isolated_environment_manifest_sha256": hashlib.sha256(
                b"isolated-geoai-environment"
            ).hexdigest(),
            "run_contract_sha256": hashlib.sha256(
                b"typed-geoai-run-contract"
            ).hexdigest(),
        }
    path = tmp_path / f"{family}-lane-contract.json"
    path.write_text(
        json.dumps({**common, "lane": lane}, sort_keys=True), encoding="utf-8"
    )
    return path


def _runner_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    del monkeypatch
    tmp_path.mkdir(parents=True, exist_ok=True)
    manifest, artifacts, authority, acquisition = _authorized_acquisition(tmp_path)
    holdout, geometry, grid_contract, membership, holdout_receipt = _holdout_fixture(
        tmp_path / "holdout", acquisition=acquisition
    )
    reference_bundle = _reference_bundle_fixture(
        tmp_path / "reference",
        acquisition,
        holdout,
        artifacts["reference_mask"],
    )
    reference = reference_bundle["reference"]
    reviewer = reference_bundle["reviewer"]
    policy_path = tmp_path / "promotion-policy.json"
    write_signed_model_promotion_policy(
        policy_path,
        policy_id="TEST-POLICY-1",
        experiment_id=acquisition.experiment_id,
        study_area=acquisition.study_area,
        issued_at_utc=datetime(2024, 1, 5, tzinfo=UTC),
        expires_at_utc=datetime(2030, 1, 1, tzinfo=UTC),
        thresholds={
            "minimum_iou": 0.0,
            "minimum_f1_dice": 0.0,
            "minimum_precision": 0.0,
            "minimum_recall": 0.0,
            "maximum_absolute_area_error_ratio": 10.0,
            "maximum_brier_score": 1.0,
            "maximum_expected_calibration_error": 1.0,
        },
        required_error_categories=REQUIRED_ERROR_CATEGORIES,
        minimum_error_category_cell_count=1,
        tie_break_order=["iou_desc", "model_id_ascending"],
        expected_artifact_filenames={
            "metrics": "three_model_metrics.csv",
            "calibration": "three_model_calibration.csv",
            "error_categories": "three_model_error_categories.csv",
            "runtime": "three_model_runtime.csv",
        },
        signing_key_id=POLICY_KEY_ID,
        signing_key=POLICY_KEY,
    )
    execution_receipt = tmp_path / "execution-authorization.json"
    controlled.write_signed_execution_authorization_receipt(
        acquisition=acquisition,
        reviewer_qualification=reviewer,
        holdout=holdout,
        reference_cells=reference,
        promotion_policy_path=policy_path,
        signing_keys=SIGNING_KEYS,
        expires_at_utc=datetime(2030, 1, 1, tzinfo=UTC),
        signing_key_id=EXECUTION_KEY_ID,
        signing_key=EXECUTION_KEY,
        output_path=execution_receipt,
    )
    execution = controlled.load_signed_execution_authorization_receipt(
        execution_receipt,
        acquisition=acquisition,
        reviewer_qualification=reviewer,
        holdout=holdout,
        calibration_reference=reference_bundle["calibration"],
        promotion_policy_path=policy_path,
        signing_keys=SIGNING_KEYS,
    )
    prediction_paths: dict[str, Path] = {}
    calibration_prediction_paths: dict[str, Path] = {}
    threshold_receipts: dict[str, Path] = {}
    model_artifacts: dict[str, Path] = {}
    model_contracts: dict[str, Path] = {}
    model_runs: dict[str, Path] = {}
    rows: list[dict[str, object]] = []
    for index, (family, frame) in enumerate(_prediction_frames().items()):
        prediction = tmp_path / f"{family}-predictions.csv"
        frame.to_csv(prediction, index=False, lineterminator="\n")
        prediction_paths[family] = prediction
        calibration_prediction = tmp_path / f"{family}-calibration-predictions.csv"
        frame.loc[frame["split"].eq("calibration")].to_csv(
            calibration_prediction,
            index=False,
            lineterminator="\n",
        )
        calibration_prediction_paths[family] = calibration_prediction
        artifact = tmp_path / f"{family}-model.bin"
        artifact.write_bytes(f"model-{family}".encode())
        model_artifacts[family] = artifact
        model_id = f"MODEL-{index}"
        model_contract = _model_lane_contract(
            tmp_path,
            family,
            model_id,
            artifact,
            execution_authorization_manifest_sha256=execution.manifest_sha256,
            configuration_frozen_at_utc=controlled._format_utc(
                execution.authorized_at_utc
            ),
        )
        model_contracts[family] = model_contract
        threshold_path = tmp_path / f"{family}-threshold.json"
        write_signed_threshold_selection_receipt(
            model_id=model_id,
            model_family=family,
            model_artifact_path=artifact,
            model_contract_path=model_contract,
            calibration_prediction_path=calibration_prediction,
            acquisition=acquisition,
            reviewer_qualification=reviewer,
            holdout=holdout,
            calibration_reference=reference_bundle["calibration"],
            execution_authorization=execution,
            execution_started_at_utc=execution.authorized_at_utc,
            training_started_at_utc=execution.authorized_at_utc
            + timedelta(microseconds=1),
            training_completed_at_utc=execution.authorized_at_utc
            + timedelta(microseconds=2),
            signing_key_id=MODEL_KEY_ID,
            signing_key=MODEL_KEY,
            output_path=threshold_path,
        )
        threshold_receipts[family] = threshold_path
        threshold_payload = json.loads(threshold_path.read_text(encoding="utf-8"))
        selected_at = controlled._timestamp(
            threshold_payload["selected_at_utc"], "selected_at_utc"
        )
        run_path = tmp_path / f"{family}-run.json"
        run = write_signed_model_run_manifest(
            model_id=model_id,
            model_family=family,
            model_artifact_path=artifact,
            model_contract_path=model_contract,
            prediction_path=prediction,
            acquisition=acquisition,
            reviewer_qualification=reviewer,
            holdout=holdout,
            reference_cells=reference,
            calibration_reference=reference_bundle["calibration"],
            execution_authorization=execution,
            threshold_selection_receipt_path=threshold_path,
            calibration_prediction_path=calibration_prediction,
            runtime_profile={
                "training_seconds": float(index * 2),
                "calibration_seconds": 0.5,
                "inference_seconds": 1.0,
                "total_seconds": float(index * 2) + 1.5,
                "peak_memory_mb": float(128 + index),
                "device": "cpu",
                "hardware_class": "synthetic-test-runner",
            },
            inference_started_at_utc=selected_at + timedelta(microseconds=1),
            completed_at_utc=selected_at + timedelta(microseconds=2),
            assumptions="Synthetic signed run fixture.",
            signing_keys=SIGNING_KEYS,
            signing_key_id=MODEL_KEY_ID,
            signing_key=MODEL_KEY,
            output_path=run_path,
        )
        model_runs[family] = run_path
        rows.append(
            {
                "model_id": model_id,
                "model_family": family,
                "prediction_file": prediction.name,
                "prediction_sha256": _sha(prediction),
                "model_artifact_file": artifact.name,
                "model_artifact_sha256": _sha(artifact),
                "model_contract_file": model_contract.name,
                "model_contract_file_sha256": _sha(model_contract),
                "model_contract_sha256": controlled._canonical_sha256(
                    json.loads(model_contract.read_text(encoding="utf-8"))
                ),
                "model_run_manifest_file": run_path.name,
                "model_run_manifest_sha256": _sha(run_path),
                "acquisition_manifest_sha256": acquisition.manifest_sha256,
                "reference_mask_sha256": acquisition.reference_mask_sha256,
                "spatial_holdout_manifest_sha256": holdout.manifest_sha256,
                "reviewer_qualification_file_sha256": reviewer.receipt_file_sha256,
                "execution_authorization_manifest_sha256": execution.manifest_sha256,
                "threshold_selection_manifest_sha256": threshold_payload[
                    "manifest_sha256"
                ],
                "completed_at_utc": run["completed_at_utc"],
                "execution_status": "completed",
                "spatial_holdout_untouched": True,
                "can_feed_decision_layer": False,
                "source_timestamp": run["completed_at_utc"],
                "confidence_class": "low",
                "assumptions": "Synthetic runner fixture.",
            }
        )
    model_evidence = tmp_path / "model-evidence.csv"
    pd.DataFrame(rows, columns=MODEL_EVIDENCE_COLUMNS).to_csv(
        model_evidence,
        index=False,
        lineterminator="\n",
    )
    return {
        "manifest": manifest,
        "artifacts": artifacts,
        "authority": authority,
        "reviewer": reference_bundle["reviewer_receipt"],
        "holdout_receipt": holdout_receipt,
        "geometry": geometry,
        "grid_contract": grid_contract,
        "membership": membership,
        "reference_evidence": reference_bundle["evidence"],
        "reference_receipt": reference_bundle["receipt"],
        "calibration_reference": reference_bundle["calibration_path"],
        "error_strata": reference_bundle["error_strata"],
        "promotion_policy": policy_path,
        "execution_authorization": execution_receipt,
        "model_evidence": model_evidence,
        "predictions": prediction_paths,
        "calibration_predictions": calibration_prediction_paths,
        "threshold_receipts": threshold_receipts,
        "model_artifacts": model_artifacts,
        "model_contracts": model_contracts,
        "model_runs": model_runs,
    }


def _run_fixture(
    fixture: dict[str, object],
    output: Path,
    *,
    result_signing_key_id: str = RESULT_KEY_ID,
    result_expires_at_utc: datetime = datetime(2030, 1, 1, tzinfo=UTC),
) -> dict[str, Path]:
    return run_controlled_three_model_experiment(
        acquisition_manifest_path=fixture["manifest"],
        acquisition_artifact_paths=fixture["artifacts"],
        acquisition_authority_receipt_path=fixture["authority"],
        reviewer_qualification_receipt_path=fixture["reviewer"],
        holdout_receipt_path=fixture["holdout_receipt"],
        holdout_geometry_path=fixture["geometry"],
        holdout_grid_contract_path=fixture["grid_contract"],
        holdout_membership_path=fixture["membership"],
        reference_cell_receipt_path=fixture["reference_receipt"],
        reference_cell_evidence_path=fixture["reference_evidence"],
        calibration_reference_path=fixture["calibration_reference"],
        error_strata_path=fixture["error_strata"],
        promotion_policy_path=fixture["promotion_policy"],
        execution_authorization_receipt_path=fixture["execution_authorization"],
        model_evidence_manifest_path=fixture["model_evidence"],
        prediction_paths=fixture["predictions"],
        calibration_prediction_paths=fixture["calibration_predictions"],
        threshold_selection_receipt_paths=fixture["threshold_receipts"],
        model_artifact_paths=fixture["model_artifacts"],
        model_contract_paths=fixture["model_contracts"],
        model_run_manifest_paths=fixture["model_runs"],
        signing_keys=SIGNING_KEYS,
        external_authority_public_keys=EXTERNAL_PUBLIC_KEYS,
        result_signing_key_id=result_signing_key_id,
        output_directory=output,
        result_expires_at_utc=result_expires_at_utc,
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
