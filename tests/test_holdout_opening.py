"""Synthetic signatures exercise expiry, scope and one-use local custody."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from test_controlled_experiment import _ed25519_public_key, _ed25519_sign

from floodguard.label_factory.holdout_opening import (
    OPENING_SCHEMA,
    HoldoutOpeningError,
    TrustedCustodyKey,
    consume_signed_holdout_opening,
    verify_signed_holdout_opening,
)

SEED = bytes(range(32))
KEY_ID = "synthetic-test-custodian"
MANIFEST_SHA = "a" * 64
RELEASE_SET_SHA = "b" * 64
HOLDOUT_SHA = "c" * 64
NOW = datetime(2026, 9, 23, 12, tzinfo=timezone.utc)


def _canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def _trust(**changes):
    values = {
        "public_key": _ed25519_public_key(SEED),
        "role": "spatial_partition_custodian",
        "valid_from_utc": "2026-09-01T00:00:00Z",
        "valid_until_utc": "2026-10-01T00:00:00Z",
    }
    values.update(changes)
    return {KEY_ID: TrustedCustodyKey(**values)}


def _receipt(tmp_path, **changes):
    payload = {
        "schema_version": OPENING_SCHEMA,
        "opening_id": "synthetic-opening-001",
        "experiment_id": "synthetic-experiment-001",
        "nonce": "synthetic-nonce-001",
        "partition_manifest_sha256": MANIFEST_SHA,
        "qualified_release_set_sha256": RELEASE_SET_SHA,
        "final_holdout_partition_sha256": HOLDOUT_SHA,
        "signing_role": "spatial_partition_custodian",
        "signing_key_id": KEY_ID,
        "issued_at_utc": "2026-09-23T09:00:00Z",
        "not_before_utc": "2026-09-23T10:00:00Z",
        "expires_at_utc": "2026-09-24T00:00:00Z",
        "opening_scope": "single_final_evaluation",
        "maximum_consumptions": 1,
        "reference_opened_before_authorization": False,
    }
    payload.update(changes)
    receipt = {
        "signed_payload": payload,
        "signature_ed25519_hex": _ed25519_sign(SEED, _canonical(payload)).hex(),
    }
    path = tmp_path / "opening.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    return path


def _arguments(receipt_file):
    return {
        "receipt_file": receipt_file,
        "trusted_keys": _trust(),
        "now_utc": NOW,
        "partition_manifest_sha256": MANIFEST_SHA,
        "qualified_release_set_sha256": RELEASE_SET_SHA,
        "final_holdout_partition_sha256": HOLDOUT_SHA,
    }


def test_synthetic_signature_checks_and_local_consumption_is_one_use(tmp_path):
    receipt = _receipt(tmp_path)
    verified = verify_signed_holdout_opening(**_arguments(receipt))
    assert verified["status"] == "signed_opening_verified_preflight_only"
    assert verified["real_experiment_authorized"] is False

    ledger = tmp_path / "external-ledger"
    ledger.mkdir()
    consumed = consume_signed_holdout_opening(
        **_arguments(receipt), external_ledger_dir=ledger
    )
    assert consumed["status"] == "local_exclusive_preflight_only"
    assert consumed["real_experiment_authorized"] is False
    marker = ledger / f"holdout-{HOLDOUT_SHA}.json"
    assert (
        json.loads(marker.read_text())["opening_receipt_sha256"]
        == verified["receipt_sha256"]
    )
    original = marker.read_bytes()
    with pytest.raises(HoldoutOpeningError, match="already been consumed"):
        consume_signed_holdout_opening(
            **_arguments(receipt), external_ledger_dir=ledger
        )
    assert marker.read_bytes() == original

    # A newly signed receipt cannot reopen the same frozen holdout split.
    second = _receipt(
        tmp_path, opening_id="synthetic-opening-002", nonce="synthetic-nonce-002"
    )
    with pytest.raises(HoldoutOpeningError, match="already been consumed"):
        consume_signed_holdout_opening(**_arguments(second), external_ledger_dir=ledger)


def test_tamper_and_untrusted_role_fail_before_consumption(tmp_path):
    receipt = _receipt(tmp_path)
    value = json.loads(receipt.read_text())
    value["signed_payload"]["experiment_id"] = "synthetic-experiment-002"
    receipt.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(HoldoutOpeningError, match="signature did not verify"):
        verify_signed_holdout_opening(**_arguments(receipt))

    receipt = _receipt(tmp_path)
    args = _arguments(receipt)
    args["trusted_keys"] = _trust(role="model_executor")
    with pytest.raises(HoldoutOpeningError, match="not trusted"):
        verify_signed_holdout_opening(**args)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"expires_at_utc": "2026-09-23T11:00:00Z"}, "expired"),
        ({"not_before_utc": "2026-09-23T13:00:00Z"}, "not yet valid"),
        ({"maximum_consumptions": 2}, "unsafe"),
        ({"reference_opened_before_authorization": True}, "unsafe"),
    ],
)
def test_stale_or_unsafe_signed_opening_fails(tmp_path, changes, message):
    receipt = _receipt(tmp_path, **changes)
    with pytest.raises(HoldoutOpeningError, match=message):
        verify_signed_holdout_opening(**_arguments(receipt))


def test_trust_expiry_and_mismatched_frozen_hash_fail(tmp_path):
    receipt = _receipt(tmp_path)
    args = _arguments(receipt)
    args["trusted_keys"] = _trust(valid_until_utc="2026-09-23T11:00:00Z")
    with pytest.raises(HoldoutOpeningError, match="trusted key lifetime"):
        verify_signed_holdout_opening(**args)

    args = _arguments(receipt)
    args["partition_manifest_sha256"] = "d" * 64
    with pytest.raises(HoldoutOpeningError, match="differs from frozen input"):
        verify_signed_holdout_opening(**args)
