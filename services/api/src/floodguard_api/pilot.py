"""Fail-closed controls for a bounded FloodGuard agency pilot."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import stat
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from floodguard_api.pilot_models import (
    MANDATORY_ACCEPTANCE_CRITERIA,
    AcceptanceReceiptPayload,
    AcceptanceReceiptRequest,
    AuditEntry,
    AuditLogResponse,
    BilingualAcceptanceCriterion,
    DeploymentMonitoringResponse,
    FieldValidationReceipt,
    OperationalArtifactManifest,
    OperationalAssessmentRequest,
    OperationalAssessmentResponse,
    PilotCredential,
    PilotReadiness,
    PilotRole,
    PilotSessionResponse,
    ReceiptVerificationResponse,
    RetentionCatalogArtifact,
    RetentionCategory,
    RetentionDecision,
    RetentionRequest,
    RetentionResponse,
    SignedAcceptanceReceipt,
    SignedRetentionCatalog,
)

ZERO_HASH = "0" * 64
NO_ACCEPTANCE_RECEIPT_BYTES = b'{"state":"not-installed"}'
NO_ACCEPTANCE_RECEIPT_SHA256 = hashlib.sha256(NO_ACCEPTANCE_RECEIPT_BYTES).hexdigest()
RETENTION_APPROVAL_PHRASE = "EXECUTE PILOT RETENTION"
REQUIRED_ACCEPTANCE_CRITERIA = MANDATORY_ACCEPTANCE_CRITERIA
PILOT_ROLES = list(PilotRole)
CAPABILITY_GRANTS: dict[PilotRole, frozenset[str]] = {
    PilotRole.PUBLIC_VIEWER: frozenset({"session:read"}),
    PilotRole.COMMAND_VIEWER: frozenset({"session:read", "monitoring:read"}),
    PilotRole.ANALYST: frozenset(
        {"session:read", "monitoring:read", "receipt:verify", "assessment:run"}
    ),
    PilotRole.DATA_STEWARD: frozenset(
        {
            "session:read",
            "monitoring:read",
            "receipt:verify",
            "assessment:run",
            "retention:dry_run",
        }
    ),
    PilotRole.PILOT_ADMIN: frozenset(
        {
            "session:read",
            "monitoring:read",
            "receipt:verify",
            "receipt:sign",
            "assessment:run",
            "retention:dry_run",
            "retention:execute",
            "audit:read",
        }
    ),
}


class PilotError(RuntimeError):
    """Base class for sanitized pilot-boundary failures."""

    status_code = 400
    error_code = "pilot_error"


class PilotCredentialError(PilotError):
    status_code = 401
    error_code = "invalid_pilot_credential"


class PilotPermissionError(PilotError):
    status_code = 403
    error_code = "pilot_permission_denied"


class PilotConfigurationError(PilotError):
    status_code = 503
    error_code = "pilot_not_configured"


class PilotReceiptError(PilotError):
    status_code = 422
    error_code = "invalid_acceptance_receipt"


class OperationalBoundaryError(PilotError):
    status_code = 409
    error_code = "agency_operational_boundary_rejected"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class PilotKeyring:
    """HMAC keyring supplied by an external secret store or test fixture."""

    def __init__(self, keys: Mapping[str, bytes], active_key_id: str | None = None) -> None:
        normalized = {str(key_id): bytes(secret) for key_id, secret in keys.items()}
        if any(len(secret) < 32 for secret in normalized.values()):
            raise ValueError("Pilot HMAC keys must contain at least 32 bytes.")
        if active_key_id is not None and active_key_id not in normalized:
            raise ValueError("Active pilot key ID is not present in the keyring.")
        self._keys = normalized
        self.active_key_id = active_key_id

    @classmethod
    def from_environment(cls) -> PilotKeyring:
        """Load base64-encoded key material without persisting or exposing it."""

        raw = os.getenv("FLOODGUARD_PILOT_KEYS_JSON", "")
        active = os.getenv("FLOODGUARD_PILOT_ACTIVE_KEY_ID") or None
        if not raw:
            return cls({}, None)
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError
            keys = {
                str(key_id): base64.b64decode(str(encoded), validate=True)
                for key_id, encoded in payload.items()
            }
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise PilotConfigurationError("Pilot key configuration is invalid.") from exc
        try:
            return cls(keys, active)
        except ValueError as exc:
            raise PilotConfigurationError("Pilot key configuration is invalid.") from exc

    @property
    def configured(self) -> bool:
        return bool(self._keys and self.active_key_id)

    def sign(self, key_id: str, payload: bytes) -> str:
        secret = self._keys.get(key_id)
        if secret is None:
            raise PilotCredentialError("Credential key ID is not trusted.")
        return hmac.new(secret, payload, hashlib.sha256).hexdigest()

    def active_sign(self, payload: bytes) -> tuple[str, str]:
        if not self.configured or self.active_key_id is None:
            raise PilotConfigurationError("Pilot signing keys are not configured.")
        return self.active_key_id, self.sign(self.active_key_id, payload)

    def verify(self, key_id: str, payload: bytes, signature: str) -> bool:
        secret = self._keys.get(key_id)
        if secret is None:
            return False
        expected = hmac.new(secret, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


def issue_test_credential(
    keyring: PilotKeyring,
    credential: PilotCredential,
) -> str:
    """Create a credential for tests or an external identity-provider adapter.

    FloodGuard exposes no token-issuing HTTP endpoint; production tokens must be
    issued outside this service and verified here on every protected request.
    """

    body = _b64url_encode(_canonical(credential.model_dump(mode="json")))
    message = f"fgp1.{body}".encode()
    signature = keyring.sign(credential.key_id, message)
    return f"fgp1.{body}.{signature}"


def audit_retention_binding_sha256(audit_instance_id: str, artifact_id: str) -> str:
    """Build a path-free binding for one role in an immutable audit instance."""

    if re.fullmatch(r"[0-9a-f]{32}", audit_instance_id) is None or artifact_id not in {
        "pilot-audit-ledger",
        "pilot-audit-anchor",
    }:
        raise ValueError("Audit retention binding inputs are invalid.")
    return hashlib.sha256(
        _canonical(
            {
                "schema_version": "1.0",
                "audit_instance_id": audit_instance_id,
                "artifact_id": artifact_id,
            }
        )
    ).hexdigest()


class AuditLedger:
    """Append-only audit chain bound to a separately mounted HMAC anchor."""

    ANCHOR_SCHEMA = "floodguard.audit-anchor.v1"

    def __init__(
        self,
        path: Path | None,
        anchor_path: Path | None,
        keyring: PilotKeyring,
    ) -> None:
        self.path = path
        self.anchor_path = anchor_path
        self.keyring = keyring
        self._lock = threading.RLock()
        self._verified_audit_instance_id: str | None = None

    @property
    def configured(self) -> bool:
        return (
            self.path is not None
            and self.anchor_path is not None
            and self.path != self.anchor_path
            and not self.path.is_symlink()
            and not self.anchor_path.is_symlink()
            and self.keyring.configured
        )

    def append(
        self,
        *,
        identity: PilotCredential,
        action: str,
        outcome: str,
        details: dict[str, Any],
        now: datetime,
    ) -> AuditEntry:
        if not self.configured or self.path is None:
            raise PilotConfigurationError("Append-only pilot audit logging is not configured.")
        with self._lock:
            anchor_bytes = _read_stable_regular_file(self.anchor_path)
            if anchor_bytes is None or self.path.is_symlink():
                raise PilotConfigurationError("Pilot audit chain integrity check failed.")
            flags = os.O_RDWR | os.O_APPEND | getattr(os, "O_BINARY", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            try:
                before = self.path.lstat()
                descriptor = os.open(self.path, flags)
            except OSError as exc:
                raise PilotConfigurationError("Pilot audit ledger open failed.") from exc
            try:
                opened = os.fstat(descriptor)
                if not stat.S_ISREG(opened.st_mode) or _file_fingerprint(
                    before
                ) != _file_fingerprint(opened):
                    raise PilotConfigurationError("Pilot audit ledger identity changed.")
                ledger_bytes = _read_descriptor_bytes(descriptor)
                records, valid = self._verify_snapshot(ledger_bytes, anchor_bytes)
                if not valid:
                    raise PilotConfigurationError("Pilot audit chain integrity check failed.")
                previous_hash = records[-1].event_hash if records else ZERO_HASH
                base = {
                    "sequence": len(records) + 1,
                    "occurred_at": now.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                    "actor_subject": identity.subject,
                    "actor_roles": [role.value for role in identity.roles],
                    "action": action,
                    "outcome": outcome,
                    "details": _redact(details),
                    "previous_hash": previous_hash,
                }
                event_hash = hashlib.sha256(_canonical(base)).hexdigest()
                key_id, authentication_code = self.keyring.active_sign(
                    f"{event_hash}:{previous_hash}".encode()
                )
                entry = AuditEntry.model_validate(
                    {
                        **base,
                        "event_hash": event_hash,
                        "key_id": key_id,
                        "authentication_code": authentication_code,
                    }
                )
                encoded_entry = (
                    json.dumps(entry.model_dump(mode="json"), sort_keys=True) + "\n"
                ).encode("utf-8")
                _write_descriptor_bytes(descriptor, encoded_entry)
                os.fsync(descriptor)
                combined = _read_descriptor_bytes(descriptor)
                after = os.fstat(descriptor)
                final = self.path.lstat()
                post_records, post_valid = self._parse_records(combined)
                if (
                    not post_valid
                    or len(post_records) != len(records) + 1
                    or post_records[-1] != entry
                    or _file_identity(opened) != _file_identity(after)
                    or _file_identity(after) != _file_identity(final)
                    or after.st_size != len(combined)
                ):
                    raise PilotConfigurationError("Pilot audit ledger changed during append.")
                self._write_anchor(
                    entry_count=len(post_records),
                    last_event_hash=entry.event_hash,
                    ledger_sha256=hashlib.sha256(combined).hexdigest(),
                )
                final_after_anchor = self.path.lstat()
                if _file_identity(after) != _file_identity(final_after_anchor):
                    raise PilotConfigurationError(
                        "Pilot audit ledger changed during anchor update."
                    )
                return entry
            except OSError as exc:
                raise PilotConfigurationError("Pilot audit append failed.") from exc
            finally:
                os.close(descriptor)

    def read(self) -> AuditLogResponse:
        with self._lock:
            records, valid = self._read_and_verify()
        return AuditLogResponse(chain_valid=valid, entry_count=len(records), entries=records)

    def state(self) -> str:
        if not self.configured:
            return "unconfigured"
        with self._lock:
            return "valid" if self._read_and_verify()[1] else "invalid"

    def _read_and_verify(self) -> tuple[list[AuditEntry], bool]:
        if not self.configured or self.path is None or self.anchor_path is None:
            return [], False
        ledger_bytes = _read_stable_regular_file(self.path)
        anchor_bytes = _read_stable_regular_file(self.anchor_path)
        if ledger_bytes is None or anchor_bytes is None:
            return [], False
        return self._verify_snapshot(ledger_bytes, anchor_bytes)

    def _verify_snapshot(
        self,
        ledger_bytes: bytes,
        anchor_bytes: bytes,
    ) -> tuple[list[AuditEntry], bool]:
        records: list[AuditEntry] = []
        try:
            anchor = _strict_json_loads(anchor_bytes)
            if not isinstance(anchor, dict) or set(anchor) != {
                "schema_version",
                "audit_instance_id",
                "entry_count",
                "last_event_hash",
                "ledger_sha256",
                "key_id",
                "authentication_code",
            }:
                return records, False
            anchor_base = {
                "schema_version": anchor.get("schema_version"),
                "audit_instance_id": anchor.get("audit_instance_id"),
                "entry_count": anchor.get("entry_count"),
                "last_event_hash": anchor.get("last_event_hash"),
                "ledger_sha256": anchor.get("ledger_sha256"),
            }
            if (
                anchor_base["schema_version"] != self.ANCHOR_SCHEMA
                or not isinstance(anchor_base["audit_instance_id"], str)
                or re.fullmatch(r"[0-9a-f]{32}", anchor_base["audit_instance_id"]) is None
                or not isinstance(anchor_base["entry_count"], int)
                or anchor_base["entry_count"] < 0
                or not _is_sha256(anchor_base["last_event_hash"])
                or not _is_sha256(anchor_base["ledger_sha256"])
                or not isinstance(anchor.get("key_id"), str)
                or not _is_sha256(anchor.get("authentication_code"))
                or not self.keyring.verify(
                    anchor["key_id"],
                    _canonical(anchor_base),
                    anchor["authentication_code"],
                )
                or not hmac.compare_digest(
                    anchor_base["ledger_sha256"],
                    hashlib.sha256(ledger_bytes).hexdigest(),
                )
            ):
                return records, False
            self._verified_audit_instance_id = anchor_base["audit_instance_id"]
            records, records_valid = self._parse_records(ledger_bytes)
            if not records_valid:
                return records, False
            expected_last = records[-1].event_hash if records else ZERO_HASH
            if anchor_base["entry_count"] != len(records) or not hmac.compare_digest(
                anchor_base["last_event_hash"], expected_last
            ):
                return records, False
        except (OSError, UnicodeError, json.JSONDecodeError, ValidationError, ValueError):
            return records, False
        return records, True

    def _parse_records(self, ledger_bytes: bytes) -> tuple[list[AuditEntry], bool]:
        records: list[AuditEntry] = []
        try:
            lines = ledger_bytes.decode("utf-8").splitlines()
            for line in lines:
                if not line.strip():
                    return records, False
                entry = AuditEntry.model_validate(_strict_json_loads(line))
                expected_previous = records[-1].event_hash if records else ZERO_HASH
                if entry.sequence != len(records) + 1 or entry.previous_hash != expected_previous:
                    return records, False
                base = entry.model_dump(
                    mode="json", exclude={"event_hash", "key_id", "authentication_code"}
                )
                expected_hash = hashlib.sha256(_canonical(base)).hexdigest()
                if not hmac.compare_digest(expected_hash, entry.event_hash):
                    return records, False
                if not self.keyring.verify(
                    entry.key_id,
                    f"{entry.event_hash}:{entry.previous_hash}".encode(),
                    entry.authentication_code,
                ):
                    return records, False
                records.append(entry)
        except (UnicodeError, json.JSONDecodeError, ValidationError, ValueError):
            return records, False
        return records, True

    def _write_anchor(
        self,
        *,
        entry_count: int,
        last_event_hash: str,
        ledger_sha256: str,
        audit_instance_id: str | None = None,
    ) -> None:
        if self.anchor_path is None:
            raise PilotConfigurationError("Pilot audit anchor is not configured.")
        instance_id = audit_instance_id or self._verified_audit_instance_id
        if instance_id is None or re.fullmatch(r"[0-9a-f]{32}", instance_id) is None:
            raise PilotConfigurationError("Pilot audit instance identity is unavailable.")
        base = {
            "schema_version": self.ANCHOR_SCHEMA,
            "audit_instance_id": instance_id,
            "entry_count": entry_count,
            "last_event_hash": last_event_hash,
            "ledger_sha256": ledger_sha256,
        }
        key_id, authentication_code = self.keyring.active_sign(_canonical(base))
        payload = (
            _canonical(
                {
                    **base,
                    "key_id": key_id,
                    "authentication_code": authentication_code,
                }
            )
            + b"\n"
        )
        temporary = self.anchor_path.with_name(f".{self.anchor_path.name}.pending")
        try:
            with temporary.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.anchor_path)
        except OSError as exc:
            raise PilotConfigurationError("Pilot audit anchor update failed.") from exc

    def audit_instance_id(self) -> str | None:
        """Return the authenticated immutable audit-instance ID, never a path."""

        with self._lock:
            if not self._read_and_verify()[1]:
                return None
            return self._verified_audit_instance_id


def provision_audit_ledger(
    *,
    ledger_path: Path,
    anchor_path: Path,
    keyring: PilotKeyring,
) -> None:
    """Provision an empty ledger plus signed genesis anchor outside normal startup."""

    if not keyring.configured or ledger_path == anchor_path:
        raise PilotConfigurationError("Audit ledger provisioning inputs are invalid.")
    if ledger_path.exists() or anchor_path.exists():
        raise PilotConfigurationError("Audit ledger provisioning refuses existing paths.")
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    anchor_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with ledger_path.open("xb") as stream:
            stream.flush()
            os.fsync(stream.fileno())
        ledger = AuditLedger(ledger_path, anchor_path, keyring)
        ledger._write_anchor(
            entry_count=0,
            last_event_hash=ZERO_HASH,
            ledger_sha256=hashlib.sha256(b"").hexdigest(),
            audit_instance_id=secrets.token_hex(16),
        )
        if ledger.state() != "valid":
            raise PilotConfigurationError("Provisioned audit genesis did not verify.")
    except Exception:
        for path in (anchor_path, ledger_path):
            try:
                if path.exists() and not path.is_symlink() and path.is_file():
                    path.unlink()
            except OSError:
                pass
        raise


_PRIVATE_PATH = re.compile(r"(?i)(?:[a-z]:[\\/]|/home/|/users/|\\\\)")
_SECRET_KEYS = re.compile(r"(?i)(?:authorization|token|secret|password|signature|key_material)")


def _redact(value: Any, key: str = "") -> Any:
    if _SECRET_KEYS.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(item_key): _redact(item, str(item_key)) for item_key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item, key) for item in value]
    if isinstance(value, str):
        if value.lower().startswith("bearer ") or _PRIVATE_PATH.search(value):
            return "[REDACTED]"
        return value[:500]
    if isinstance(value, bool | int | float) or value is None:
        return value
    return str(value)[:500]


@dataclass(frozen=True)
class ControlEvidenceSnapshot:
    """Exact descriptor-bound bytes used for retention and evidence parsing."""

    artifact_manifest_bytes: bytes
    field_validation_receipt_bytes: bytes
    acceptance_receipt_bytes: bytes


class RetentionEngine:
    """Apply retention from signed server evidence, never caller timestamps or holds."""

    POLICY_VERSION = "agency-pilot-retention-v1"
    RETAIN_DAYS: dict[RetentionCategory, int | None] = {
        RetentionCategory.ACCEPTANCE_RECEIPT: None,
        RetentionCategory.AUDIT_LOG: None,
        RetentionCategory.SOURCE_MANIFEST: 730,
        RetentionCategory.DERIVED_CANDIDATE: 90,
        RetentionCategory.TEMPORARY: 7,
    }

    QUARANTINE_NAME = ".retention-quarantine"

    def __init__(
        self,
        root: Path | None,
        catalog_path: Path | None,
        keyring: PilotKeyring,
        clock: Any | None = None,
    ) -> None:
        self.root = root
        self.catalog_path = catalog_path
        self.keyring = keyring
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.RLock()

    @property
    def configured(self) -> bool:
        root = self._governed_root()
        if root is None or self._quarantine(root) is None:
            return False
        return self._load_catalog(now=self._clock().astimezone(UTC)) is not None

    def capture_control_evidence(
        self,
        *,
        audit_ledger_path: Path | None,
        audit_anchor_path: Path | None,
        audit_instance_id: str | None,
        acceptance_receipt_bytes: bytes | None,
        acceptance_receipt_path: Path | None,
        require_acceptance_path: bool,
        artifact_manifest_path: Path | None,
        field_validation_receipt_path: Path | None,
    ) -> ControlEvidenceSnapshot | None:
        """Capture exact mounted bytes while proving catalog/path identity."""

        root = self._governed_root()
        loaded = self._load_catalog(now=self._clock().astimezone(UTC))
        if (
            root is None
            or self._quarantine(root) is None
            or loaded is None
            or audit_instance_id is None
        ):
            return None
        catalog, _ = loaded
        indexed = {item.artifact_id: item for item in catalog.payload.artifacts}

        for artifact_id, actual_path in {
            "pilot-audit-ledger": audit_ledger_path,
            "pilot-audit-anchor": audit_anchor_path,
        }.items():
            item = indexed.get(artifact_id)
            target = self._catalog_target_path(root, item)
            snapshot = _read_bound_regular_file(actual_path, target)
            if (
                item is None
                or target is None
                or actual_path is None
                or snapshot is None
                or not hmac.compare_digest(
                    item.evidence_binding_sha256,
                    audit_retention_binding_sha256(audit_instance_id, artifact_id),
                )
            ):
                return None

        immutable_snapshots: dict[str, BoundRegularFileSnapshot] = {}
        for artifact_id, actual_path in {
            "current-served-artifact-manifest": artifact_manifest_path,
            "current-field-validation-receipt": field_validation_receipt_path,
        }.items():
            item = indexed.get(artifact_id)
            target = self._catalog_target_path(root, item)
            snapshot = _read_bound_regular_file(actual_path, target)
            if (
                item is None
                or target is None
                or actual_path is None
                or snapshot is None
                or not _catalog_digest_matches(item, snapshot.content)
            ):
                return None
            immutable_snapshots[artifact_id] = snapshot

        acceptance = indexed.get("pilot-acceptance-receipt")
        acceptance_target = self._catalog_target_path(root, acceptance)
        acceptance_source = (
            acceptance_receipt_path if require_acceptance_path else acceptance_target
        )
        acceptance_snapshot = _read_bound_regular_file(
            acceptance_source,
            acceptance_target,
        )
        if (
            acceptance is None
            or acceptance_target is None
            or acceptance_snapshot is None
            or (
                acceptance_receipt_bytes is not None
                and not hmac.compare_digest(
                    acceptance_snapshot.content,
                    acceptance_receipt_bytes,
                )
            )
            or not _catalog_digest_matches(acceptance, acceptance_snapshot.content)
        ):
            return None
        return ControlEvidenceSnapshot(
            artifact_manifest_bytes=immutable_snapshots["current-served-artifact-manifest"].content,
            field_validation_receipt_bytes=immutable_snapshots[
                "current-field-validation-receipt"
            ].content,
            acceptance_receipt_bytes=acceptance_snapshot.content,
        )

    def evaluate(
        self,
        request: RetentionRequest,
        *,
        now: datetime,
    ) -> RetentionResponse:
        root = self._governed_root()
        loaded = self._load_catalog(now=now)
        if root is None or self._quarantine(root) is None or loaded is None:
            raise PilotConfigurationError("External pilot artifact retention is not configured.")
        if request.mode == "execute" and request.approval_phrase != RETENTION_APPROVAL_PHRASE:
            raise PilotPermissionError("Retention execution requires the exact approval phrase.")
        catalog, catalog_sha256 = loaded
        indexed = {item.artifact_id: item for item in catalog.payload.artifacts}
        if any(artifact_id not in indexed for artifact_id in request.artifact_ids):
            raise PilotPermissionError(
                "Retention request names an artifact absent from the signed catalog."
            )
        with self._lock:
            decisions = [
                self._evaluate_one(indexed[artifact_id], request.mode, root, now)
                for artifact_id in request.artifact_ids
            ]
        return RetentionResponse(
            policy_version=self.POLICY_VERSION,
            catalog_sha256=catalog_sha256,
            mode=request.mode,
            evaluated_at=now,
            decisions=decisions,
            deleted_count=sum(decision.deleted for decision in decisions),
        )

    def _evaluate_one(
        self,
        artifact: RetentionCatalogArtifact,
        mode: str,
        root: Path,
        now: datetime,
    ) -> RetentionDecision:
        target = root.joinpath(*artifact.relative_path.split("/"))
        parent_fingerprints = _stable_directory_chain(root, target.parent)
        if parent_fingerprints is None:
            return self._decision(artifact, "blocked", "Artifact path escaped the retention root.")
        if target.is_symlink():
            return self._decision(
                artifact, "blocked", "Symbolic links are never retention targets."
            )
        artifact_read = _read_stable_regular_file_with_stat(target)
        if artifact_read is None:
            if not target.exists():
                return self._decision(artifact, "missing", "Artifact is already absent.")
            return self._decision(artifact, "blocked", "Only stable regular files may be removed.")
        artifact_bytes, artifact_stat = artifact_read
        if not hmac.compare_digest(hashlib.sha256(artifact_bytes).hexdigest(), artifact.sha256):
            return self._decision(
                artifact,
                "blocked",
                "Artifact bytes do not match the signed retention catalog.",
            )
        if not target.exists():
            return self._decision(artifact, "missing", "Artifact is already absent.")
        if artifact.legal_hold:
            return self._decision(artifact, "retain", "Legal hold overrides expiration.")
        days = self.RETAIN_DAYS[artifact.category]
        if days is None:
            return self._decision(artifact, "retain", "Category is retained indefinitely.")
        created_at = artifact.created_at.astimezone(UTC)
        now_utc = now.astimezone(UTC)
        if created_at > now_utc:
            return self._decision(artifact, "blocked", "Future-dated artifacts require review.")
        age_days = (now_utc - created_at).total_seconds() / 86400
        if age_days < days:
            return self._decision(
                artifact,
                "retain",
                f"Artifact is inside the {days}-day retention window.",
            )
        deleted = False
        if mode == "execute":
            deleted = self._quarantine_rehash_delete(
                artifact=artifact,
                target=target,
                root=root,
                source_stat=artifact_stat,
                parent_fingerprints=parent_fingerprints,
            )
            if not deleted:
                return self._decision(
                    artifact,
                    "blocked",
                    "Artifact identity changed during governed quarantine; nothing was deleted.",
                )
        return self._decision(
            artifact,
            "delete",
            f"Artifact exceeded the {days}-day retention window.",
            deleted=deleted,
        )

    @staticmethod
    def _decision(
        artifact: RetentionCatalogArtifact,
        disposition: str,
        reason: str,
        *,
        deleted: bool = False,
    ) -> RetentionDecision:
        return RetentionDecision(
            artifact_id=artifact.artifact_id,
            relative_path=artifact.relative_path,
            category=artifact.category,
            disposition=disposition,
            reason=reason,
            deleted=deleted,
        )

    def _governed_root(self) -> Path | None:
        if self.root is None or self.root.is_symlink():
            return None
        try:
            root_stat = self.root.lstat()
            if not stat.S_ISDIR(root_stat.st_mode):
                return None
            lexical = Path(os.path.abspath(self.root))
            resolved = self.root.resolve(strict=True)
            if lexical != resolved:
                return None
        except OSError:
            return None
        return resolved

    def _quarantine(self, root: Path) -> Path | None:
        quarantine = root / self.QUARANTINE_NAME
        if quarantine.is_symlink():
            return None
        try:
            root_stat = root.lstat()
            quarantine_stat = quarantine.lstat()
        except OSError:
            return None
        if (
            not stat.S_ISDIR(quarantine_stat.st_mode)
            or root_stat.st_dev != quarantine_stat.st_dev
            or (os.name != "nt" and quarantine_stat.st_mode & 0o077)
        ):
            return None
        return quarantine

    def _load_catalog(
        self,
        *,
        now: datetime,
    ) -> tuple[SignedRetentionCatalog, str] | None:
        catalog_bytes = _read_stable_regular_file(self.catalog_path)
        if catalog_bytes is None:
            return None
        try:
            catalog = SignedRetentionCatalog.model_validate(_strict_json_loads(catalog_bytes))
        except (UnicodeError, ValueError, ValidationError):
            return None
        payload_bytes = _canonical(catalog.payload.model_dump(mode="json"))
        payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()
        if (
            not hmac.compare_digest(payload_sha256, catalog.signature.payload_sha256)
            or not self.keyring.verify(
                catalog.signature.key_id,
                payload_bytes,
                catalog.signature.value,
            )
            or catalog.payload.generated_at > now.astimezone(UTC)
            or catalog.payload.review_due_at <= now.astimezone(UTC)
        ):
            return None
        return catalog, hashlib.sha256(catalog_bytes).hexdigest()

    def _catalog_target_path(
        self,
        root: Path,
        artifact: RetentionCatalogArtifact | None,
    ) -> Path | None:
        if artifact is None:
            return None
        target = root.joinpath(*artifact.relative_path.split("/"))
        if target.is_symlink() or _stable_directory_chain(root, target.parent) is None:
            return None
        try:
            target_stat = target.lstat()
        except OSError:
            return None
        return target if stat.S_ISREG(target_stat.st_mode) else None

    def _quarantine_rehash_delete(
        self,
        *,
        artifact: RetentionCatalogArtifact,
        target: Path,
        root: Path,
        source_stat: os.stat_result,
        parent_fingerprints: tuple[tuple[Path, tuple[int, int, int]], ...],
    ) -> bool:
        quarantine = self._quarantine(root)
        if quarantine is None:
            return False
        root_before = _directory_fingerprint(root)
        quarantine_before = _directory_fingerprint(quarantine)
        if root_before is None or quarantine_before is None:
            return False
        pending = quarantine / f"{artifact.artifact_id}.{artifact.sha256}.pending"
        if pending.exists() or pending.is_symlink():
            return False
        try:
            os.replace(target, pending)
        except OSError:
            return False
        moved = _read_stable_regular_file_with_stat(pending)
        directories_stable = (
            root_before == _directory_fingerprint(root)
            and quarantine_before == _directory_fingerprint(quarantine)
            and parent_fingerprints == _stable_directory_chain(root, target.parent)
        )
        if moved is None or not directories_stable:
            return False
        moved_bytes, moved_stat = moved
        same_identity = (
            source_stat.st_dev == moved_stat.st_dev
            and source_stat.st_ino == moved_stat.st_ino
            and source_stat.st_size == moved_stat.st_size
        )
        if not same_identity or not hmac.compare_digest(
            hashlib.sha256(moved_bytes).hexdigest(), artifact.sha256
        ):
            return False
        try:
            pending.unlink()
        except OSError:
            return False
        return True


class PilotControl:
    """Coordinates identity, receipts, audit, retention, and status boundaries."""

    def __init__(
        self,
        *,
        keyring: PilotKeyring,
        audit_log_path: Path | None = None,
        audit_anchor_path: Path | None = None,
        artifact_root: Path | None = None,
        retention_catalog_path: Path | None = None,
        installed_receipt: SignedAcceptanceReceipt | None = None,
        installed_receipt_path: Path | None = None,
        current_artifact_manifest_path: Path | None = None,
        current_field_validation_receipt_path: Path | None = None,
        audit_writer_mode: str = "single_process",
        clock: Any | None = None,
    ) -> None:
        if audit_log_path is not None and audit_writer_mode != "single_process":
            raise PilotConfigurationError(
                "The JSONL audit ledger supports single-process writing only."
            )
        self.keyring = keyring
        self._clock = clock or (lambda: datetime.now(UTC))
        self.audit = AuditLedger(audit_log_path, audit_anchor_path, keyring)
        self.retention = RetentionEngine(
            artifact_root,
            retention_catalog_path,
            keyring,
            clock=self._clock,
        )
        self.installed_receipt = installed_receipt
        self.installed_receipt_path = installed_receipt_path
        self.current_artifact_manifest_path = current_artifact_manifest_path
        self.current_field_validation_receipt_path = current_field_validation_receipt_path

    @classmethod
    def from_environment(cls) -> PilotControl:
        keyring = PilotKeyring.from_environment()
        receipt = None
        configured_receipt: Path | None = None
        receipt_path = os.getenv("FLOODGUARD_PILOT_ACCEPTANCE_RECEIPT")
        if receipt_path:
            configured_receipt = Path(receipt_path)
            receipt_bytes = _read_stable_regular_file(configured_receipt)
            if receipt_bytes is None:
                raise PilotConfigurationError(
                    "Configured acceptance receipt must be a regular non-symlink file."
                )
            try:
                receipt = SignedAcceptanceReceipt.model_validate(_strict_json_loads(receipt_bytes))
            except (UnicodeError, ValueError, ValidationError) as exc:
                raise PilotConfigurationError("Configured acceptance receipt is invalid.") from exc
        audit = os.getenv("FLOODGUARD_PILOT_AUDIT_LOG")
        audit_anchor = os.getenv("FLOODGUARD_PILOT_AUDIT_ANCHOR")
        artifacts = os.getenv("FLOODGUARD_PILOT_ARTIFACT_ROOT")
        retention_catalog = os.getenv("FLOODGUARD_PILOT_RETENTION_CATALOG")
        if bool(audit) != bool(audit_anchor):
            raise PilotConfigurationError(
                "Audit ledger and external anchor must be configured together."
            )
        writer_mode = os.getenv("FLOODGUARD_PILOT_AUDIT_WRITER_MODE", "")
        try:
            configured_workers = max(
                int(os.getenv("WEB_CONCURRENCY", "1")),
                int(os.getenv("UVICORN_WORKERS", "1")),
            )
        except ValueError as exc:
            raise PilotConfigurationError("Configured API worker count is invalid.") from exc
        if audit and (writer_mode != "single_process" or configured_workers != 1):
            raise PilotConfigurationError(
                "JSONL audit logging requires explicit single_process mode and one API worker."
            )
        return cls(
            keyring=keyring,
            audit_log_path=Path(audit) if audit else None,
            audit_anchor_path=Path(audit_anchor) if audit_anchor else None,
            artifact_root=Path(artifacts) if artifacts else None,
            retention_catalog_path=(Path(retention_catalog) if retention_catalog else None),
            installed_receipt=receipt,
            installed_receipt_path=configured_receipt,
            current_artifact_manifest_path=(
                Path(value)
                if (value := os.getenv("FLOODGUARD_PILOT_CURRENT_ARTIFACT_MANIFEST"))
                else None
            ),
            current_field_validation_receipt_path=(
                Path(value)
                if (value := os.getenv("FLOODGUARD_PILOT_CURRENT_FIELD_VALIDATION_RECEIPT"))
                else None
            ),
            audit_writer_mode=writer_mode or "single_process",
        )

    def now(self) -> datetime:
        return self._clock().astimezone(UTC)

    def authenticate(self, authorization: str | None) -> PilotCredential:
        if not authorization or not authorization.startswith("Bearer "):
            raise PilotCredentialError("A bearer credential is required.")
        token = authorization.removeprefix("Bearer ").strip()
        try:
            prefix, body, signature = token.split(".")
            if prefix != "fgp1" or not re.fullmatch(r"[0-9a-f]{64}", signature):
                raise ValueError
            raw = _b64url_decode(body)
            credential = PilotCredential.model_validate(_strict_json_loads(raw))
        except (ValueError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
            raise PilotCredentialError("Pilot credential is malformed.") from exc
        if not self.keyring.verify(credential.key_id, f"fgp1.{body}".encode(), signature):
            raise PilotCredentialError("Pilot credential signature is invalid.")
        now = self.now()
        if credential.expires_at <= now:
            raise PilotCredentialError("Pilot credential has expired.")
        if credential.issued_at > now:
            raise PilotCredentialError("Pilot credential is not active yet.")
        return credential

    def require(self, identity: PilotCredential, capability: str) -> None:
        granted = self.capabilities(identity)
        if capability not in granted:
            if self.audit.configured:
                self.audit.append(
                    identity=identity,
                    action=f"authorize:{capability}",
                    outcome="denied",
                    details={"reason": "role_matrix"},
                    now=self.now(),
                )
            raise PilotPermissionError("The authenticated role cannot perform this operation.")

    @staticmethod
    def capabilities(identity: PilotCredential) -> list[str]:
        return sorted(set().union(*(CAPABILITY_GRANTS[role] for role in identity.roles)))

    def session(self, identity: PilotCredential) -> PilotSessionResponse:
        return PilotSessionResponse(
            subject=identity.subject,
            roles=identity.roles,
            expires_at=identity.expires_at,
            granted_capabilities=self.capabilities(identity),
        )

    def sign_acceptance(
        self,
        request: AcceptanceReceiptRequest,
        identity: PilotCredential,
    ) -> SignedAcceptanceReceipt:
        self.require(identity, "receipt:sign")
        now = self.now()
        context = self._capture_evidence_context(
            acceptance_receipt=None,
            require_acceptance_path=False,
        )
        if context is None:
            raise PilotConfigurationError(
                "Acceptance signing requires configured keys, a valid audit chain, "
                "and governed retention."
            )
        if request.dataset_mode != "official_input":
            raise PilotReceiptError(
                "Fixture and candidate datasets cannot receive acceptance receipts."
            )
        _, current_evidence = context
        if not current_evidence.matches(
            study_area=request.study_area,
            data_version=request.data_version,
            source_timestamp=request.source_timestamp,
            artifact_manifest_sha256=request.artifact_manifest_sha256,
            field_validation_receipt_sha256=request.field_validation_receipt_sha256,
        ):
            raise PilotReceiptError(
                "Acceptance request is not bound to the current evidence files and scope."
            )
        if request.expires_at <= now:
            raise PilotReceiptError("Acceptance receipt expiry must be in the future.")
        if request.expires_at - now > timedelta(days=30):
            raise PilotReceiptError("Acceptance receipts may be valid for at most 30 days.")
        if not REQUIRED_ACCEPTANCE_CRITERIA.issubset(request.acceptance_criteria_ids):
            raise PilotReceiptError("All mandatory bilingual acceptance criteria must be accepted.")
        payload = AcceptanceReceiptPayload(
            acceptance_id=request.acceptance_id,
            study_area=request.study_area,
            dataset_mode="official_input",
            data_version=request.data_version,
            artifact_manifest_sha256=request.artifact_manifest_sha256,
            source_timestamp=request.source_timestamp,
            acceptance_criteria_ids=request.acceptance_criteria_ids,
            field_validation_receipt_sha256=request.field_validation_receipt_sha256,
            field_validation_protocol_version=request.field_validation_protocol_version,
            issued_at=now,
            expires_at=request.expires_at,
            issuer_subject=identity.subject,
        )
        payload_bytes = _canonical(payload.model_dump(mode="json"))
        payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()
        key_id, value = self.keyring.active_sign(payload_bytes)
        receipt = SignedAcceptanceReceipt.model_validate(
            {
                "payload": payload,
                "signature": {
                    "algorithm": "HMAC-SHA256",
                    "key_id": key_id,
                    "payload_sha256": payload_sha256,
                    "value": value,
                },
            }
        )
        self.audit.append(
            identity=identity,
            action="acceptance_receipt:sign",
            outcome="completed",
            details={
                "acceptance_id": payload.acceptance_id,
                "study_area": payload.study_area,
                "data_version": payload.data_version,
                "payload_sha256": payload_sha256,
            },
            now=now,
        )
        return receipt

    def verify_receipt(self, receipt: SignedAcceptanceReceipt) -> ReceiptVerificationResponse:
        payload_bytes = _canonical(receipt.payload.model_dump(mode="json"))
        digest = hashlib.sha256(payload_bytes).hexdigest()
        if not hmac.compare_digest(digest, receipt.signature.payload_sha256):
            return ReceiptVerificationResponse(
                valid=False,
                acceptance_id=receipt.payload.acceptance_id,
                acceptance_status="rejected",
                reason="Receipt payload checksum does not match.",
            )
        if not self.keyring.verify(
            receipt.signature.key_id,
            payload_bytes,
            receipt.signature.value,
        ):
            return ReceiptVerificationResponse(
                valid=False,
                acceptance_id=receipt.payload.acceptance_id,
                acceptance_status="rejected",
                reason="Receipt signature is invalid or its key is not trusted.",
            )
        now = self.now()
        if receipt.payload.issued_at > now:
            return ReceiptVerificationResponse(
                valid=False,
                acceptance_id=receipt.payload.acceptance_id,
                acceptance_status="rejected",
                reason="Receipt is not active yet.",
            )
        if receipt.payload.expires_at <= now:
            return ReceiptVerificationResponse(
                valid=False,
                acceptance_id=receipt.payload.acceptance_id,
                acceptance_status="rejected",
                reason="Receipt has expired.",
            )
        if not REQUIRED_ACCEPTANCE_CRITERIA.issubset(receipt.payload.acceptance_criteria_ids):
            return ReceiptVerificationResponse(
                valid=False,
                acceptance_id=receipt.payload.acceptance_id,
                acceptance_status="rejected",
                reason="Receipt omits mandatory acceptance criteria.",
            )
        return ReceiptVerificationResponse(
            valid=True,
            acceptance_id=receipt.payload.acceptance_id,
            acceptance_status="accepted",
            reason="Receipt signature, expiry, and acceptance criteria are valid.",
        )

    def assess(self, request: OperationalAssessmentRequest) -> OperationalAssessmentResponse:
        if request.dataset_mode != "official_input":
            return OperationalAssessmentResponse(
                operational_status="non_operational",
                acceptance_receipt_valid=False,
                reason="Fixture and candidate datasets are always non-operational.",
            )
        if request.receipt is None:
            return OperationalAssessmentResponse(
                operational_status="planning_only",
                acceptance_receipt_valid=False,
                reason="Official input remains planning-only without a signed acceptance receipt.",
            )
        verification = self.verify_receipt(request.receipt)
        if not verification.valid:
            return OperationalAssessmentResponse(
                operational_status="planning_only",
                acceptance_receipt_valid=False,
                reason="Acceptance receipt is invalid or bound to different evidence.",
            )
        context = self._capture_evidence_context(
            acceptance_receipt=request.receipt,
            require_acceptance_path=False,
        )
        if context is None:
            return OperationalAssessmentResponse(
                operational_status="planning_only",
                acceptance_receipt_valid=True,
                reason=(
                    "Receipt is valid, but keys, audit integrity, and retention controls "
                    "must all be ready."
                ),
            )
        _, current_evidence = context
        if not self._receipt_matches_current_evidence(
            receipt=request.receipt,
            study_area=request.study_area,
            data_version=request.data_version,
            artifact_manifest_sha256=request.expected_artifact_manifest_sha256,
            field_validation_receipt_sha256=request.expected_field_validation_receipt_sha256,
            current_evidence=current_evidence,
        ):
            return OperationalAssessmentResponse(
                operational_status="planning_only",
                acceptance_receipt_valid=False,
                reason="Acceptance receipt is invalid or bound to different evidence.",
            )
        return OperationalAssessmentResponse(
            operational_status="agency_operational",
            acceptance_receipt_valid=True,
            reason="Signed acceptance receipt matches the official-input evidence.",
        )

    def assert_operational_boundary(self, value: Any) -> None:
        payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
        self._assert_payload(payload)

    def _assert_payload(self, value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                self._assert_payload(item)
            return
        if not isinstance(value, dict):
            return
        if value.get("operational_status") == "agency_operational":
            if value.get("dataset_mode") != "official_input":
                raise OperationalBoundaryError(
                    "Fixture and candidate payloads cannot become agency operational."
                )
            if self.installed_receipt is None:
                raise OperationalBoundaryError(
                    "Agency-operational output requires an externally installed acceptance receipt."
                )
            context = self._capture_evidence_context(
                acceptance_receipt=self.installed_receipt,
                require_acceptance_path=True,
            )
            if context is None:
                raise OperationalBoundaryError(
                    "Agency-operational output requires configured keys, a valid audit chain, "
                    "governed retention, and hashable current artifact and field-validation "
                    "receipt files."
                )
            _, current_evidence = context
            if not current_evidence.covers_payload(value):
                raise OperationalBoundaryError(
                    "Agency-operational response is absent from the accepted served-response "
                    "lineage manifest."
                )
            if not self.verify_receipt(self.installed_receipt).valid or not (
                self._receipt_matches_current_evidence(
                    receipt=self.installed_receipt,
                    study_area=str(
                        value.get("study_area") or self.installed_receipt.payload.study_area
                    ),
                    data_version=str(value.get("data_version") or ""),
                    artifact_manifest_sha256=current_evidence.artifact_manifest_sha256,
                    field_validation_receipt_sha256=(
                        current_evidence.field_validation_receipt_sha256
                    ),
                    current_evidence=current_evidence,
                )
            ):
                raise OperationalBoundaryError(
                    "Installed acceptance receipt does not match the response evidence."
                )
        for item in value.values():
            self._assert_payload(item)

    def readiness(
        self,
        *,
        dataset_mode: str,
        study_area: str,
        data_version: str,
        served_payload: Any | None = None,
    ) -> PilotReadiness:
        receipt_state = self._receipt_state()
        context = self._capture_evidence_context(
            acceptance_receipt=self.installed_receipt,
            require_acceptance_path=self.installed_receipt is not None,
        )
        current_evidence = context[1] if context is not None else None
        retention_ready = context is not None
        allowed = False
        if (
            dataset_mode == "official_input"
            and self.installed_receipt is not None
            and current_evidence is not None
            and self.verify_receipt(self.installed_receipt).valid
            and self._receipt_matches_current_evidence(
                receipt=self.installed_receipt,
                study_area=study_area,
                data_version=data_version,
                artifact_manifest_sha256=current_evidence.artifact_manifest_sha256,
                field_validation_receipt_sha256=(current_evidence.field_validation_receipt_sha256),
                current_evidence=current_evidence,
            )
            and served_payload is not None
            and current_evidence.covers_payload(
                served_payload.model_dump(mode="json")
                if hasattr(served_payload, "model_dump")
                else served_payload
            )
        ):
            allowed = True
        identity_state = "configured" if self.keyring.configured else "unconfigured"
        audit_state = self.audit.state()
        retention_state = "configured" if retention_ready else "unconfigured"
        if allowed:
            deployment_state = "accepted_for_agency_operation"
            status = "agency_operational"
            blocked_th = ""
            blocked_en = ""
        elif "invalid" in {receipt_state, audit_state} or (
            receipt_state == "accepted" and current_evidence is None
        ):
            deployment_state = "degraded"
            status = "non_operational"
            blocked_th = "หลักฐานการยอมรับ ไฟล์หลักฐานปัจจุบัน หรือห่วงโซ่บันทึกตรวจสอบไม่ถูกต้อง"
            blocked_en = (
                "Acceptance evidence, current evidence files, or the audit chain is invalid."
            )
        elif self.keyring.configured and self.audit.configured and retention_ready:
            deployment_state = "pilot_ready_non_operational"
            status = "planning_only" if dataset_mode == "official_input" else "non_operational"
            blocked_th = "รอใบรับรองการยอมรับที่ลงนามและตรงกับข้อมูลทางการ"
            blocked_en = "Waiting for a signed acceptance receipt bound to official evidence."
        else:
            deployment_state = "pilot_not_configured"
            status = "non_operational"
            blocked_th = "โหมดสาธิตไม่ได้กำหนดข้อมูลประจำตัว บันทึกตรวจสอบ หรือพื้นที่เก็บภายนอก"
            blocked_en = "Demo mode has no identity, audit, or external retention configuration."
        criteria = [
            BilingualAcceptanceCriterion(
                criterion_id=criterion_id,
                status="accepted" if allowed else "pending",
                text_th=th,
                text_en=en,
            )
            for criterion_id, th, en in _acceptance_criteria()
        ]
        return PilotReadiness(
            operational_status=status,
            agency_operational_allowed=allowed,
            identity_state=identity_state,
            acceptance_receipt_state=receipt_state,
            audit_state=audit_state,
            retention_state=retention_state,
            deployment_state=deployment_state,
            acceptance_criteria=criteria,
            field_validation_protocol_version="field-validation-v1",
            roles=PILOT_ROLES,
            reason_blocked_th=blocked_th,
            reason_blocked_en=blocked_en,
        )

    def monitoring(
        self,
        *,
        dataset_mode: str,
        study_area: str,
        data_version: str,
        data_state: str,
        source_timestamp: datetime,
        served_payload: Any,
    ) -> DeploymentMonitoringResponse:
        readiness = self.readiness(
            dataset_mode=dataset_mode,
            study_area=study_area,
            data_version=data_version,
            served_payload=served_payload,
        )
        control_degraded = readiness.deployment_state == "degraded"
        return DeploymentMonitoringResponse(
            service_health="degraded" if control_degraded else "healthy",
            deployment_state=readiness.deployment_state,
            identity_state=readiness.identity_state,
            audit_chain_state=readiness.audit_state,
            retention_state=readiness.retention_state,
            acceptance_receipt_state=readiness.acceptance_receipt_state,
            data_freshness_state=data_state,
            data_source_timestamp=source_timestamp,
            checked_at=self.now(),
            operational_status=readiness.operational_status,
        )

    def run_retention(
        self,
        request: RetentionRequest,
        identity: PilotCredential,
    ) -> RetentionResponse:
        capability = "retention:execute" if request.mode == "execute" else "retention:dry_run"
        self.require(identity, capability)
        if not self._control_plane_ready(
            acceptance_receipt=self.installed_receipt,
            require_acceptance_path=self.installed_receipt is not None,
        ):
            raise PilotConfigurationError(
                "Retention requires configured keys, a valid audit chain, and governed storage."
            )
        if request.mode == "execute":
            self.audit.append(
                identity=identity,
                action="retention:execute_intent",
                outcome="allowed",
                details={"artifact_ids": request.artifact_ids},
                now=self.now(),
            )
        response = self.retention.evaluate(request, now=self.now())
        self.audit.append(
            identity=identity,
            action=f"retention:{request.mode}",
            outcome="completed",
            details={
                "policy_version": response.policy_version,
                "artifact_ids": request.artifact_ids,
                "catalog_sha256": response.catalog_sha256,
                "deleted_count": response.deleted_count,
            },
            now=self.now(),
        )
        return response

    def _receipt_state(self) -> str:
        if self.installed_receipt is None:
            return "missing"
        result = self.verify_receipt(self.installed_receipt)
        if result.valid:
            return "accepted"
        if "expired" in result.reason.lower():
            return "expired"
        return "invalid"

    def _control_plane_ready(
        self,
        *,
        acceptance_receipt: SignedAcceptanceReceipt | None,
        require_acceptance_path: bool,
    ) -> bool:
        return (
            self._capture_evidence_context(
                acceptance_receipt=acceptance_receipt,
                require_acceptance_path=require_acceptance_path,
            )
            is not None
        )

    def _capture_evidence_context(
        self,
        *,
        acceptance_receipt: SignedAcceptanceReceipt | None,
        require_acceptance_path: bool,
    ) -> tuple[ControlEvidenceSnapshot, CurrentEvidenceBinding] | None:
        if (
            not self.keyring.configured
            or not self.audit.configured
            or self.audit.state() != "valid"
        ):
            return None
        if acceptance_receipt is None:
            acceptance_bytes = NO_ACCEPTANCE_RECEIPT_BYTES
            acceptance_path = None
        elif require_acceptance_path:
            acceptance_path = self.installed_receipt_path
            acceptance_bytes = None
        else:
            acceptance_path = None
            acceptance_bytes = _canonical(acceptance_receipt.model_dump(mode="json"))
        snapshot = self.retention.capture_control_evidence(
            audit_ledger_path=self.audit.path,
            audit_anchor_path=self.audit.anchor_path,
            audit_instance_id=self.audit.audit_instance_id(),
            acceptance_receipt_bytes=acceptance_bytes,
            acceptance_receipt_path=acceptance_path,
            require_acceptance_path=require_acceptance_path,
            artifact_manifest_path=self.current_artifact_manifest_path,
            field_validation_receipt_path=self.current_field_validation_receipt_path,
        )
        if snapshot is None:
            return None
        if acceptance_receipt is not None:
            try:
                mounted = SignedAcceptanceReceipt.model_validate(
                    _strict_json_loads(snapshot.acceptance_receipt_bytes)
                )
            except (UnicodeError, ValueError, ValidationError):
                return None
            if mounted != acceptance_receipt:
                return None
        current_evidence = self._current_evidence(snapshot)
        if current_evidence is None:
            return None
        return snapshot, current_evidence

    def _current_evidence(
        self,
        snapshot: ControlEvidenceSnapshot,
    ) -> CurrentEvidenceBinding | None:
        artifact_bytes = snapshot.artifact_manifest_bytes
        field_bytes = snapshot.field_validation_receipt_bytes
        try:
            artifact_manifest = OperationalArtifactManifest.model_validate(
                _strict_json_loads(artifact_bytes)
            )
            field_receipt = FieldValidationReceipt.model_validate(_strict_json_loads(field_bytes))
        except (UnicodeError, ValueError, ValidationError):
            return None
        if field_receipt.status != "accepted":
            return None
        now = self.now()
        if (
            artifact_manifest.source_timestamp > now
            or field_receipt.source_timestamp > now
            or field_receipt.generated_at > now
            or field_receipt.issued_at > now
            or field_receipt.review_due_at <= now
        ):
            return None
        return CurrentEvidenceBinding(
            artifact_manifest_sha256=hashlib.sha256(artifact_bytes).hexdigest(),
            field_validation_receipt_sha256=hashlib.sha256(field_bytes).hexdigest(),
            artifact_manifest=artifact_manifest,
            field_study_area=field_receipt.study_area,
            field_data_version=field_receipt.data_version,
            field_source_timestamp=field_receipt.source_timestamp,
        )

    def _receipt_matches_current_evidence(
        self,
        *,
        receipt: SignedAcceptanceReceipt,
        study_area: str,
        data_version: str,
        artifact_manifest_sha256: str,
        field_validation_receipt_sha256: str,
        current_evidence: CurrentEvidenceBinding,
    ) -> bool:
        return (
            receipt.payload.study_area == study_area
            and receipt.payload.data_version == data_version
            and hmac.compare_digest(
                receipt.payload.artifact_manifest_sha256,
                artifact_manifest_sha256,
            )
            and hmac.compare_digest(
                receipt.payload.field_validation_receipt_sha256,
                field_validation_receipt_sha256,
            )
            and current_evidence.matches(
                study_area=study_area,
                data_version=data_version,
                source_timestamp=receipt.payload.source_timestamp,
                artifact_manifest_sha256=artifact_manifest_sha256,
                field_validation_receipt_sha256=field_validation_receipt_sha256,
            )
        )


@dataclass(frozen=True)
class CurrentEvidenceBinding:
    """Byte digests plus scope fields extracted from both mounted evidence files."""

    artifact_manifest_sha256: str
    field_validation_receipt_sha256: str
    artifact_manifest: OperationalArtifactManifest
    field_study_area: str
    field_data_version: str
    field_source_timestamp: datetime

    def matches(
        self,
        *,
        study_area: str,
        data_version: str,
        source_timestamp: datetime,
        artifact_manifest_sha256: str,
        field_validation_receipt_sha256: str,
    ) -> bool:
        return all(
            (
                hmac.compare_digest(self.artifact_manifest.study_area, study_area),
                hmac.compare_digest(self.artifact_manifest.data_version, data_version),
                hmac.compare_digest(self.field_study_area, study_area),
                hmac.compare_digest(self.field_data_version, data_version),
                self.artifact_manifest.source_timestamp == source_timestamp,
                self.field_source_timestamp == source_timestamp,
                hmac.compare_digest(
                    self.artifact_manifest_sha256,
                    artifact_manifest_sha256,
                ),
                hmac.compare_digest(
                    self.field_validation_receipt_sha256,
                    field_validation_receipt_sha256,
                ),
            )
        )

    def covers_payload(self, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        source_timestamp = _coerce_datetime(payload.get("source_timestamp"))
        data_version = payload.get("data_version")
        study_area = payload.get("study_area", self.artifact_manifest.study_area)
        if (
            source_timestamp is None
            or not isinstance(data_version, str)
            or not isinstance(study_area, str)
            or source_timestamp != self.artifact_manifest.source_timestamp
            or not hmac.compare_digest(data_version, self.artifact_manifest.data_version)
            or not hmac.compare_digest(study_area, self.artifact_manifest.study_area)
        ):
            return False
        try:
            response_sha256 = hashlib.sha256(_canonical(payload)).hexdigest()
        except (TypeError, ValueError):
            return False
        return any(
            hmac.compare_digest(item.response_sha256, response_sha256)
            and item.source_timestamp == source_timestamp
            and hmac.compare_digest(item.data_version, data_version)
            and bool(item.artifacts)
            for item in self.artifact_manifest.served_responses
        )


def _strict_json_loads(value: str | bytes) -> Any:
    """Decode JSON while rejecting duplicate object keys at trust boundaries."""

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("Duplicate JSON object key.")
            result[key] = item
        return result

    def reject_non_finite(constant: str) -> None:
        raise ValueError(f"Non-finite JSON constant is not allowed: {constant}")

    return json.loads(
        value,
        object_pairs_hook=unique_object,
        parse_constant=reject_non_finite,
    )


def _read_stable_regular_file(path: Path | None) -> bytes | None:
    """Read a stable regular file while rejecting symlinks and mid-read mutation."""

    if path is None or path.is_symlink():
        return None
    content = bytearray()
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode):
            return None
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if _file_fingerprint(before) != _file_fingerprint(opened):
                return None
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                content.extend(chunk)
            after = os.fstat(stream.fileno())
        final = path.lstat()
    except OSError:
        return None
    stable = stat.S_ISREG(final.st_mode) and _file_fingerprint(opened) == _file_fingerprint(
        after
    ) == _file_fingerprint(final)
    return bytes(content) if stable else None


@dataclass(frozen=True)
class BoundRegularFileSnapshot:
    """Bytes and identity captured from one descriptor bound to two names."""

    content: bytes
    identity: tuple[int, int, int]


def _read_bound_regular_file(
    configured_path: Path | None,
    catalog_path: Path | None,
) -> BoundRegularFileSnapshot | None:
    if (
        configured_path is None
        or catalog_path is None
        or configured_path.is_symlink()
        or catalog_path.is_symlink()
    ):
        return None
    content = bytearray()
    try:
        configured_before = configured_path.lstat()
        catalog_before = catalog_path.lstat()
        if (
            not stat.S_ISREG(configured_before.st_mode)
            or not stat.S_ISREG(catalog_before.st_mode)
            or _file_identity(configured_before) != _file_identity(catalog_before)
        ):
            return None
        with configured_path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if _file_fingerprint(configured_before) != _file_fingerprint(
                opened
            ) or _file_fingerprint(catalog_before) != _file_fingerprint(opened):
                return None
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                content.extend(chunk)
            after = os.fstat(stream.fileno())
        configured_final = configured_path.lstat()
        catalog_final = catalog_path.lstat()
    except OSError:
        return None
    if not (
        _file_fingerprint(opened)
        == _file_fingerprint(after)
        == _file_fingerprint(configured_final)
        == _file_fingerprint(catalog_final)
    ):
        return None
    return BoundRegularFileSnapshot(
        content=bytes(content),
        identity=_file_identity(opened),
    )


def _read_descriptor_bytes(descriptor: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    content = bytearray()
    while chunk := os.read(descriptor, 1024 * 1024):
        content.extend(chunk)
    return bytes(content)


def _write_descriptor_bytes(descriptor: int, value: bytes) -> None:
    view = memoryview(value)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("Audit descriptor write made no progress.")
        view = view[written:]


def _read_stable_regular_file_with_stat(
    path: Path | None,
) -> tuple[bytes, os.stat_result] | None:
    """Return stable bytes plus the opened object identity for race checks."""

    if path is None or path.is_symlink():
        return None
    content = bytearray()
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode):
            return None
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if _file_fingerprint(before) != _file_fingerprint(opened):
                return None
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                content.extend(chunk)
            after = os.fstat(stream.fileno())
        final = path.lstat()
    except OSError:
        return None
    if not (
        stat.S_ISREG(final.st_mode)
        and _file_fingerprint(opened) == _file_fingerprint(after) == _file_fingerprint(final)
    ):
        return None
    return bytes(content), final


def _directory_fingerprint(path: Path) -> tuple[int, int, int] | None:
    if path.is_symlink():
        return None
    try:
        value = path.lstat()
    except OSError:
        return None
    if not stat.S_ISDIR(value.st_mode):
        return None
    return (value.st_dev, value.st_ino, value.st_mode)


def _stable_directory_chain(
    root: Path,
    parent: Path,
) -> tuple[tuple[Path, tuple[int, int, int]], ...] | None:
    try:
        relative = parent.relative_to(root)
    except ValueError:
        return None
    current = root
    result: list[tuple[Path, tuple[int, int, int]]] = []
    for part in (Path(), *relative.parts):
        if part != Path():
            current = current / part
        fingerprint = _directory_fingerprint(current)
        if fingerprint is None:
            return None
        result.append((current, fingerprint))
    return tuple(result)


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _same_file(first: Path, second: Path) -> bool:
    try:
        return first.samefile(second)
    except OSError:
        return False


def _catalog_digest_matches(
    artifact: RetentionCatalogArtifact,
    actual_bytes: bytes,
) -> bool:
    digest = hashlib.sha256(actual_bytes).hexdigest()
    return hmac.compare_digest(artifact.sha256, digest) and hmac.compare_digest(
        artifact.evidence_binding_sha256,
        digest,
    )


def _coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _file_fingerprint(file_stat: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        file_stat.st_dev,
        file_stat.st_ino,
        file_stat.st_mode,
        file_stat.st_size,
        file_stat.st_mtime_ns,
    )


def _file_identity(file_stat: os.stat_result) -> tuple[int, int, int]:
    return (file_stat.st_dev, file_stat.st_ino, file_stat.st_mode)


def _acceptance_criteria() -> list[tuple[str, str, str]]:
    return [
        (
            "AC-SAFETY-01",
            "ข้อความภาษาไทยและอังกฤษระบุว่า FloodGuard เป็นเครื่องมือสนับสนุน"
            "การวางแผน ไม่ใช่ประกาศเตือนภัยทางการ",
            "Thai and English wording identifies FloodGuard as planning support, "
            "not an official warning.",
        ),
        (
            "AC-DATA-02",
            "ทุกหน้าจอตัดสินใจแสดงเวลาข้อมูล ความเชื่อมั่น สมมติฐาน และแหล่งที่มา",
            "Every decision screen exposes source time, confidence, assumptions, and provenance.",
        ),
        (
            "AC-OFFLINE-03",
            "ชุดข้อมูลออฟไลน์และข้อมูลสาธิตยังคงเป็น non-operational เสมอ",
            "Offline and fixture data always remain non-operational.",
        ),
        (
            "AC-AUTH-04",
            "สิทธิ์ตามบทบาทได้รับการตรวจซ้ำที่ API และการอนุญาตหรือปฏิเสธถูกบันทึก",
            "Role permissions are rechecked by the API and allowed or denied actions are audited.",
        ),
        (
            "AC-FIELD-05",
            "มีใบรับรองการตรวจสอบภาคสนามตาม field-validation-v1 และผูกกับ manifest ที่ไม่เปลี่ยนแปลง",
            "A field-validation-v1 receipt is bound to the immutable artifact manifest.",
        ),
    ]
