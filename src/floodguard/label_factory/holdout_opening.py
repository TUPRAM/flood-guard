"""Signed, one-use final-holdout opening preflight.

The caller must supply independently governed trusted public keys and a
durable external receipt store. This helper does not grant model execution or
turn a fixture partition into real custody authority.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from floodguard.controlled_experiment import _ed25519_verify

OPENING_SCHEMA = "floodguard.final_holdout_opening.v1"
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SIGNED_FIELDS = {
    "schema_version",
    "opening_id",
    "experiment_id",
    "nonce",
    "partition_manifest_sha256",
    "qualified_release_set_sha256",
    "final_holdout_partition_sha256",
    "signing_role",
    "signing_key_id",
    "issued_at_utc",
    "not_before_utc",
    "expires_at_utc",
    "opening_scope",
    "maximum_consumptions",
    "reference_opened_before_authorization",
}


class HoldoutOpeningError(ValueError):
    """Raised when signed opening custody is missing, stale or replayed."""


@dataclass(frozen=True)
class TrustedCustodyKey:
    """Public key and lifetime supplied by an external authority registry."""

    public_key: bytes
    role: str
    valid_from_utc: str
    valid_until_utc: str


def verify_signed_holdout_opening(
    receipt_file: Path,
    *,
    trusted_keys: dict[str, TrustedCustodyKey],
    now_utc: datetime,
    partition_manifest_sha256: str,
    qualified_release_set_sha256: str,
    final_holdout_partition_sha256: str,
) -> dict[str, Any]:
    """Verify signature, scope, trust lifetime and expiry without consuming."""

    receipt = _read_receipt(receipt_file)
    if set(receipt) != {"signed_payload", "signature_ed25519_hex"}:
        raise HoldoutOpeningError("opening receipt fields are not exact")
    payload = receipt["signed_payload"]
    if not isinstance(payload, dict) or set(payload) != _SIGNED_FIELDS:
        raise HoldoutOpeningError("signed opening payload fields are not exact")
    if payload["schema_version"] != OPENING_SCHEMA:
        raise HoldoutOpeningError("unsupported opening schema")
    for field in ("opening_id", "experiment_id", "nonce", "signing_key_id"):
        if not isinstance(payload[field], str) or not _SAFE_ID.fullmatch(
            payload[field]
        ):
            raise HoldoutOpeningError(f"invalid {field}")
    if (
        payload["signing_role"] != "spatial_partition_custodian"
        or payload["opening_scope"] != "single_final_evaluation"
        or type(payload["maximum_consumptions"]) is not int
        or payload["maximum_consumptions"] != 1
        or payload["reference_opened_before_authorization"] is not False
    ):
        raise HoldoutOpeningError("opening scope or unopened reference state is unsafe")
    expected = {
        "partition_manifest_sha256": partition_manifest_sha256,
        "qualified_release_set_sha256": qualified_release_set_sha256,
        "final_holdout_partition_sha256": final_holdout_partition_sha256,
    }
    for field, digest in expected.items():
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise HoldoutOpeningError(f"expected {field} is not a SHA-256 digest")
        if payload[field] != digest:
            raise HoldoutOpeningError(f"opening {field} differs from frozen input")

    key = trusted_keys.get(payload["signing_key_id"])
    if key is None or key.role != "spatial_partition_custodian":
        raise HoldoutOpeningError("custodian key is not trusted for this role")
    if not isinstance(key.public_key, bytes) or len(key.public_key) != 32:
        raise HoldoutOpeningError("trusted custodian public key is invalid")
    try:
        signature = bytes.fromhex(receipt["signature_ed25519_hex"])
    except (TypeError, ValueError) as error:
        raise HoldoutOpeningError("opening signature is invalid hex") from error
    if len(signature) != 64 or not _ed25519_verify(
        key.public_key, signature, _canonical_bytes(payload)
    ):
        raise HoldoutOpeningError("opening signature did not verify")

    now = _utc(now_utc, "now_utc")
    issued = _utc(payload["issued_at_utc"], "issued_at_utc")
    not_before = _utc(payload["not_before_utc"], "not_before_utc")
    expires = _utc(payload["expires_at_utc"], "expires_at_utc")
    key_from = _utc(key.valid_from_utc, "trusted key valid_from_utc")
    key_until = _utc(key.valid_until_utc, "trusted key valid_until_utc")
    if not (key_from <= issued <= not_before < expires <= key_until):
        raise HoldoutOpeningError("opening chronology exceeds trusted key lifetime")
    if not (not_before <= now < expires):
        raise HoldoutOpeningError("opening is not yet valid or has expired")
    return {
        "signed_payload": payload,
        "receipt_sha256": hashlib.sha256(_canonical_bytes(receipt)).hexdigest(),
        "verified_at_utc": now.isoformat().replace("+00:00", "Z"),
        "status": "signed_opening_verified_preflight_only",
        "real_experiment_authorized": False,
    }


def consume_signed_holdout_opening(
    receipt_file: Path,
    *,
    trusted_keys: dict[str, TrustedCustodyKey],
    now_utc: datetime,
    partition_manifest_sha256: str,
    qualified_release_set_sha256: str,
    final_holdout_partition_sha256: str,
    external_ledger_dir: Path,
) -> dict[str, Any]:
    """Verify, then exclusively record one local consumption per holdout split.

    The ledger directory must exist outside the code repository and be kept
    immutable by its owner. Exclusive file creation blocks local replay, but
    cannot prove external WORM storage or human authority on its own.
    """

    verified = verify_signed_holdout_opening(
        receipt_file,
        trusted_keys=trusted_keys,
        now_utc=now_utc,
        partition_manifest_sha256=partition_manifest_sha256,
        qualified_release_set_sha256=qualified_release_set_sha256,
        final_holdout_partition_sha256=final_holdout_partition_sha256,
    )
    ledger_dir = Path(external_ledger_dir)
    if _has_symlink_component(ledger_dir) or not ledger_dir.is_dir():
        raise HoldoutOpeningError(
            "external consumption ledger must exist as a directory"
        )
    marker = ledger_dir / f"holdout-{final_holdout_partition_sha256}.json"
    consumption = {
        "schema_version": "floodguard.local_holdout_consumption.v1",
        "status": "local_exclusive_preflight_only",
        "opening_id": verified["signed_payload"]["opening_id"],
        "experiment_id": verified["signed_payload"]["experiment_id"],
        "opening_receipt_sha256": verified["receipt_sha256"],
        "partition_manifest_sha256": partition_manifest_sha256,
        "qualified_release_set_sha256": qualified_release_set_sha256,
        "final_holdout_partition_sha256": final_holdout_partition_sha256,
        "consumed_at_utc": verified["verified_at_utc"],
        "real_experiment_authorized": False,
    }
    try:
        with marker.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(consumption, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise HoldoutOpeningError(
            "final holdout opening has already been consumed"
        ) from error
    except OSError as error:
        raise HoldoutOpeningError(
            f"cannot record holdout consumption: {error}"
        ) from error
    return consumption


def _read_receipt(path: Path) -> dict[str, Any]:
    source = Path(path)
    if _has_symlink_component(source):
        raise HoldoutOpeningError("opening receipt symlink is forbidden")
    try:
        before = source.stat()
        if not stat.S_ISREG(before.st_mode) or before.st_size > 128 * 1024:
            raise HoldoutOpeningError("opening receipt must be a small regular file")
        receipt = json.loads(source.read_text(encoding="utf-8"))
        if _file_identity(source.stat()) != _file_identity(before):
            raise HoldoutOpeningError("opening receipt changed during read")
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise HoldoutOpeningError(f"cannot read opening receipt: {error}") from error
    if not isinstance(receipt, dict):
        raise HoldoutOpeningError("opening receipt root must be an object")
    return receipt


def _utc(value: str | datetime, label: str) -> datetime:
    try:
        timestamp = (
            value
            if isinstance(value, datetime)
            else datetime.fromisoformat(value.replace("Z", "+00:00"))
        )
    except (AttributeError, ValueError) as error:
        raise HoldoutOpeningError(f"{label} must be a UTC timestamp") from error
    if timestamp.utcoffset() != timedelta(0):
        raise HoldoutOpeningError(f"{label} must be a UTC timestamp")
    return timestamp


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise HoldoutOpeningError("opening contains noncanonical values") from error


def _file_identity(metadata: os.stat_result) -> tuple[int, int, int, int]:
    return metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns


def _has_symlink_component(path: Path) -> bool:
    current = path
    while True:
        if current.is_symlink():
            return True
        if current.parent == current:
            return False
        current = current.parent
