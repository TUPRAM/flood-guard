"""Build an immutable, fail-closed data-rights clearance package.

This module records an accountable owner's self-attested use decision.  It
does not provide legal advice, grant third-party rights, validate flood truth,
or approve any scientific reviewer.  Provider-specific conditions remain
attached to every affirmative redistribution decision.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from collections.abc import Sequence
from typing import Any, Mapping, TypeAlias

from floodguard.label_factory.event_registry import (
    EventRecord,
    EventRegistryError,
    SourceAssetRecord,
    load_events,
    load_source_assets,
)


DECISION_SCHEMA = "floodguard_rights_owner_decision_v1"
PACKAGE_SCHEMA = "floodguard_governance_clearance_package_v1"
TIMESTAMP_BASIS = "user_declared_utc_accepted_without_independent_clock_verification"
REDISTRIBUTION_STATUS = "YES_WITH_CONDITIONS"
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_UTC_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
_PACKAGE_ID_RE = re.compile(r"governance_cleared_v[1-9]\d*")

APPROVED_SOURCE_IDS = (
    "sentinel1",
    "jrc_global_surface_water",
    "esa_worldcover_2021",
    "copernicus_dem_glo30",
)
APPROVAL_FIELDS = (
    "local_processing",
    "ml_label_derivation",
    "blinded_reviewer_display",
    "redistribution_requested",
)
REQUIRED_PENDING_FILES = frozenset(
    {
        "aligned_context_inventory.csv",
        "canonical_gate_check.json",
        "events.csv",
        "human_role_approval_ledger.csv",
        "pilot_scope_decisions.csv",
        "processed_sar_inventory.csv",
        "README.md",
        "safe_manifest_inventory.csv",
        "source_assets.csv",
    }
)

CLEARED_CONTENT_ROLES = {
    "README.md": "cleared_package_handoff",
    "aligned_context_inventory.csv": "conditionally_cleared_context_registry",
    "events.csv": "conditionally_cleared_event_registry",
    "human_role_approval_ledger.csv": "human_governance_ledger",
    "pending_package_verification.json": "verified_parent_package_evidence",
    "pilot_scope_decisions.csv": "scope_and_rights_decision_ledger",
    "prior_pending_gate_check.json": "historical_fail_closed_gate_evidence",
    "processed_sar_inventory.csv": "conditionally_cleared_processed_sar_inventory",
    "rights_owner_decision_input_v1.json": "normalized_owner_decision_input",
    "rights_owner_declaration_v1.md": "owner_self_attestation",
    "safe_manifest_inventory.csv": "unchanged_safe_provenance",
    "source_assets.csv": "conditionally_cleared_sentinel_registry",
    "source_pending_package_manifest.csv": "parent_package_manifest_snapshot",
    "source_rights_decisions_v1.csv": "source_specific_rights_conditions",
}
_PACKAGE_SEAL_KEYS = frozenset(
    {
        "adjudicator_assigned",
        "decision_timestamp_utc",
        "eligible_for_decision_layer",
        "eligible_for_fpps",
        "eligible_for_warning",
        "organization",
        "owner_name",
        "package_id",
        "package_manifest_sha256",
        "package_schema",
        "query_model_only",
        "redistribution_status",
        "reference_authority_assigned",
        "reviewers_assigned",
        "rights_status",
        "seal_kind",
        "seal_sha256",
        "source_pending_package_manifest_sha256",
        "timestamp_basis",
        "validation_allowed",
    }
)
_HUMAN_ROLE_IDS = frozenset(
    {
        "RIGHTS-OWNER",
        "REFERENCE-AUTHORITY",
        "REVIEWER-A",
        "REVIEWER-B",
        "ADJUDICATOR-C",
    }
)

RegistryInput: TypeAlias = Sequence[EventRecord] | Sequence[SourceAssetRecord] | str | Path

SENTINEL_RAW_NOTICE = "Copernicus Sentinel data 2024"
SENTINEL_MODIFIED_NOTICE = "Contains modified Copernicus Sentinel data 2024"
JRC_ATTRIBUTION = "Source: EC JRC/Google"
JRC_CITATION = (
    "Pekel, J.-F., Cottam, A., Gorelick, N., and Belward, A. S. (2016), "
    "High-resolution mapping of global surface water and its long-term changes, "
    "Nature 540, 418-422, https://doi.org/10.1038/nature20584"
)
WORLDCOVER_ATTRIBUTION = (
    "© ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data "
    "(2021) processed by ESA WorldCover consortium"
)
WORLDCOVER_CITATION = (
    "Zanaga, D. et al. (2022), ESA WorldCover 10 m 2021 v200, "
    "https://doi.org/10.5281/zenodo.7254221"
)
COPDEM_RAW_NOTICE = (
    "© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 "
    "provided under COPERNICUS by the European Union and ESA; all rights reserved"
)
COPDEM_MODIFIED_NOTICE = (
    "produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and "
    "© Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS "
    "by the European Union and ESA; all rights reserved"
)
COPDEM_ARTICLE_6C_NOTICE = (
    "The organisations in charge of the Copernicus programme by law or by "
    "delegation do not incur any liability for any use of the Copernicus "
    "WorldDEM-30"
)


class RightsClearanceError(ValueError):
    """Raised when a rights decision or source package is incomplete or unsafe."""


@dataclass(frozen=True)
class RightsOwnerDecision:
    """Typed, explicit self-attested decision for the four approved sources."""

    owner_name: str
    organization: str
    decision_timestamp_utc: str
    sources: Mapping[str, Mapping[str, bool]]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> RightsOwnerDecision:
        """Parse the strict JSON-compatible decision contract."""

        if value.get("schema") != DECISION_SCHEMA:
            raise RightsClearanceError(
                f"Decision schema must be exactly {DECISION_SCHEMA!r}."
            )
        owner = _non_blank(value.get("owner_name"), "owner_name")
        organization = _non_blank(value.get("organization"), "organization")
        timestamp = _strict_utc(value.get("decision_timestamp_utc"))
        source_values = value.get("sources")
        if not isinstance(source_values, Mapping):
            raise RightsClearanceError("sources must be an object.")
        if set(source_values) != set(APPROVED_SOURCE_IDS):
            missing = sorted(set(APPROVED_SOURCE_IDS) - set(source_values))
            extra = sorted(set(source_values) - set(APPROVED_SOURCE_IDS))
            raise RightsClearanceError(
                f"sources must contain exactly the four approved sources; "
                f"missing={missing}, extra={extra}."
            )

        normalized: dict[str, dict[str, bool]] = {}
        for source_id in APPROVED_SOURCE_IDS:
            approval = source_values[source_id]
            if not isinstance(approval, Mapping):
                raise RightsClearanceError(f"sources.{source_id} must be an object.")
            if set(approval) != set(APPROVAL_FIELDS):
                missing = sorted(set(APPROVAL_FIELDS) - set(approval))
                extra = sorted(set(approval) - set(APPROVAL_FIELDS))
                raise RightsClearanceError(
                    f"sources.{source_id} must contain exactly {APPROVAL_FIELDS}; "
                    f"missing={missing}, extra={extra}."
                )
            typed: dict[str, bool] = {}
            for field in APPROVAL_FIELDS:
                raw = approval[field]
                if not isinstance(raw, bool):
                    raise RightsClearanceError(
                        f"sources.{source_id}.{field} must be a JSON boolean."
                    )
                if raw is not True:
                    raise RightsClearanceError(
                        f"sources.{source_id}.{field}=false cannot produce a "
                        "cleared package. Build a pending/denied decision instead."
                    )
                typed[field] = raw
            normalized[source_id] = typed
        return cls(owner, organization, timestamp, normalized)


def load_rights_owner_decision(path: str | Path) -> RightsOwnerDecision:
    """Load a strict rights-owner decision JSON without accepting coercions."""

    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RightsClearanceError(f"Cannot read decision JSON {source}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise RightsClearanceError("Decision JSON root must be an object.")
    return RightsOwnerDecision.from_mapping(payload)


def validate_pending_package(pending_directory: str | Path) -> dict[str, Any]:
    """Verify every size and SHA-256 declared by the pending package manifest."""

    pending = Path(pending_directory)
    if not pending.is_dir():
        raise RightsClearanceError(f"Pending package directory does not exist: {pending}")
    manifest_path = pending / "package_manifest.csv"
    fields, rows = _read_csv(manifest_path)
    required_fields = {
        "file_name",
        "file_size_bytes",
        "sha256",
        "artifact_role",
        "immutable_status",
    }
    if not required_fields.issubset(fields):
        raise RightsClearanceError(
            "Pending package_manifest.csv lacks required columns: "
            f"{sorted(required_fields - set(fields))}."
        )
    if not rows:
        raise RightsClearanceError("Pending package_manifest.csv must not be empty.")

    verified: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(rows, start=2):
        name = _safe_relative_name(row.get("file_name", ""), index)
        if name in seen:
            raise RightsClearanceError(
                f"Pending package manifest contains duplicate file_name {name!r}."
            )
        seen.add(name)
        expected_hash = str(row.get("sha256", "")).lower()
        if not _SHA256_RE.fullmatch(expected_hash):
            raise RightsClearanceError(
                f"Pending package manifest row {index} has invalid SHA-256."
            )
        try:
            expected_size = int(str(row.get("file_size_bytes", "")))
        except ValueError as exc:
            raise RightsClearanceError(
                f"Pending package manifest row {index} has invalid file size."
            ) from exc
        if expected_size < 0:
            raise RightsClearanceError(
                f"Pending package manifest row {index} has a negative file size."
            )
        artifact = pending / Path(name)
        if not artifact.is_file():
            raise RightsClearanceError(f"Manifested pending file is missing: {name}")
        observed_size = artifact.stat().st_size
        observed_hash = _file_sha256(artifact)
        if observed_size != expected_size:
            raise RightsClearanceError(
                f"Pending file size mismatch for {name}: expected {expected_size}, "
                f"observed {observed_size}."
            )
        if observed_hash != expected_hash:
            raise RightsClearanceError(
                f"Pending file SHA-256 mismatch for {name}: expected "
                f"{expected_hash}, observed {observed_hash}."
            )
        verified.append(
            {
                "file_name": name,
                "file_size_bytes": observed_size,
                "sha256": observed_hash,
                "artifact_role": row["artifact_role"],
                "immutable_status": row["immutable_status"],
            }
        )
    missing = sorted(REQUIRED_PENDING_FILES - seen)
    if missing:
        raise RightsClearanceError(
            f"Pending package manifest does not bind required files: {missing}."
        )
    return {
        "verification_schema": "floodguard_pending_package_verification_v1",
        "pending_package_manifest_sha256": _file_sha256(manifest_path),
        "verified_file_count": len(verified),
        "all_manifested_files_verified": True,
        "files": verified,
    }


def build_rights_clearance_package(
    pending_directory: str | Path,
    output_directory: str | Path,
    decision: RightsOwnerDecision | Mapping[str, Any],
) -> Path:
    """Build and atomically publish one immutable cleared-governance package."""

    pending = Path(pending_directory).resolve()
    output = Path(output_directory).resolve()
    typed = (
        decision
        if isinstance(decision, RightsOwnerDecision)
        else RightsOwnerDecision.from_mapping(decision)
    )
    if output.exists():
        raise RightsClearanceError(f"Output already exists and is immutable: {output}")
    package_id = output.name
    if _PACKAGE_ID_RE.fullmatch(package_id) is None:
        raise RightsClearanceError(
            "Output directory name must be governance_cleared_v followed by a "
            "positive integer."
        )
    if pending == output or pending in output.parents:
        raise RightsClearanceError(
            "Output must not be the pending package or a child of it."
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    verification = validate_pending_package(pending)

    staging = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=output.parent)
    )
    try:
        _build_files(pending, staging, typed, verification, package_id)
        validate_rights_clearance_package(staging, expected_package_id=package_id)
        if output.exists():
            raise RightsClearanceError(
                f"Output appeared during build and will not be replaced: {output}"
            )
        staging.rename(output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return output


def validate_rights_clearance_package(
    directory: str | Path,
    *,
    expected_package_id: str | None = None,
) -> dict[str, Any]:
    """Rehash and semantically validate one complete clearance package.

    A content hash proves only that bytes did not change after the manifest was
    written.  This validator also proves that the bound bytes retain the exact
    fail-closed governance meanings required by the label factory.
    """

    root = Path(directory)
    if not root.is_dir():
        raise RightsClearanceError(
            f"Cleared package directory does not exist: {root}"
        )
    manifest = root / "package_manifest.csv"
    seal_path = root / "package_seal.json"
    fields, rows = _read_csv(manifest)
    expected_manifest_fields = {
        "file_name",
        "file_size_bytes",
        "sha256",
        "artifact_role",
        "immutable_status",
    }
    if set(fields) != expected_manifest_fields:
        raise RightsClearanceError("Cleared package manifest has an invalid schema.")
    manifest_rows: dict[str, dict[str, str]] = {}
    for index, row in enumerate(rows, start=2):
        name = _safe_relative_name(row["file_name"], index)
        if name in manifest_rows:
            raise RightsClearanceError(f"Duplicate cleared artifact {name!r}.")
        expected_role = CLEARED_CONTENT_ROLES.get(name)
        if expected_role is None:
            raise RightsClearanceError(
                f"Cleared package manifest contains unexpected artifact {name!r}."
            )
        if row["artifact_role"] != expected_role:
            raise RightsClearanceError(
                f"Cleared artifact role mismatch for {name}."
            )
        if row["immutable_status"] != "frozen_cleared_v1":
            raise RightsClearanceError(
                f"Cleared artifact immutable status mismatch for {name}."
            )
        artifact = root / name
        if not artifact.is_file():
            raise RightsClearanceError(f"Cleared artifact is missing: {name}")
        expected_sha = str(row["sha256"]).lower()
        if _SHA256_RE.fullmatch(expected_sha) is None:
            raise RightsClearanceError(
                f"Cleared artifact has invalid SHA-256: {name}"
            )
        try:
            expected_size = int(row["file_size_bytes"])
        except (TypeError, ValueError) as exc:
            raise RightsClearanceError(
                f"Cleared artifact has invalid file size: {name}"
            ) from exc
        if expected_size < 0 or artifact.stat().st_size != expected_size:
            raise RightsClearanceError(f"Cleared artifact size mismatch: {name}")
        if _file_sha256(artifact) != expected_sha:
            raise RightsClearanceError(f"Cleared artifact SHA-256 mismatch: {name}")
        manifest_rows[name] = dict(row)
    if set(manifest_rows) != set(CLEARED_CONTENT_ROLES):
        missing = sorted(set(CLEARED_CONTENT_ROLES) - set(manifest_rows))
        raise RightsClearanceError(
            f"Cleared package manifest lacks exact required artifacts: {missing}."
        )
    actual_files = {path.name for path in root.iterdir() if path.is_file()}
    expected_files = set(CLEARED_CONTENT_ROLES) | {
        "package_manifest.csv",
        "package_seal.json",
    }
    if actual_files != expected_files:
        raise RightsClearanceError(
            "Cleared package directory must contain exactly the sealed artifact set; "
            f"missing={sorted(expected_files - actual_files)}, "
            f"extra={sorted(actual_files - expected_files)}."
        )
    if "package_manifest.csv" in manifest_rows or "package_seal.json" in manifest_rows:
        raise RightsClearanceError(
            "Manifest and seal must be bound by the seal, not recursively listed."
        )
    try:
        seal = json.loads(seal_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RightsClearanceError(f"Cannot read package seal: {exc}") from exc
    if not isinstance(seal, Mapping) or set(seal) != _PACKAGE_SEAL_KEYS:
        raise RightsClearanceError(
            "Cleared package seal has unexpected or missing fields."
        )
    if seal.get("package_schema") != PACKAGE_SCHEMA:
        raise RightsClearanceError("Cleared package seal schema is invalid.")
    package_id = seal.get("package_id")
    expected_id = expected_package_id or root.name
    if (
        not isinstance(package_id, str)
        or _PACKAGE_ID_RE.fullmatch(package_id) is None
        or package_id != expected_id
    ):
        raise RightsClearanceError(
            "Cleared package ID must be a versioned ID matching its directory name."
        )
    if seal.get("package_manifest_sha256") != _file_sha256(manifest):
        raise RightsClearanceError("Cleared package manifest seal mismatch.")
    claimed = seal.get("seal_sha256")
    unsigned = dict(seal)
    unsigned.pop("seal_sha256", None)
    if claimed != _json_sha256(unsigned):
        raise RightsClearanceError("Cleared package seal self-hash mismatch.")
    _validate_seal_safety(seal)

    decision_path = root / "rights_owner_decision_input_v1.json"
    try:
        decision_payload = json.loads(decision_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RightsClearanceError(
            f"Cannot read normalized rights-owner decision: {exc}"
        ) from exc
    if not isinstance(decision_payload, Mapping):
        raise RightsClearanceError("Normalized rights-owner decision must be an object.")
    decision = RightsOwnerDecision.from_mapping(decision_payload)
    _require_identity_consistency(seal, decision, label="package seal")
    _validate_source_rights_rows(root, decision)
    _validate_human_roles(root, decision)
    _validate_cleared_registries(root)
    _validate_scope_decision(root, decision)
    _validate_parent_package_binding(root, seal)
    _validate_declaration(root, decision)
    return dict(seal)


def validate_cleared_registry_binding(
    directory: str | Path,
    events: Sequence[EventRecord] | str | Path,
    source_assets: Sequence[SourceAssetRecord] | str | Path,
) -> dict[str, str]:
    """Bind exact normalized event/source registries to a validated package."""

    root = Path(directory)
    seal = validate_rights_clearance_package(root)
    if isinstance(events, (str, Path)) and _file_sha256(Path(events)) != _file_sha256(
        root / "events.csv"
    ):
        raise RightsClearanceError(
            "Supplied events.csv is not byte-identical to the cleared package."
        )
    if isinstance(source_assets, (str, Path)) and _file_sha256(
        Path(source_assets)
    ) != _file_sha256(root / "source_assets.csv"):
        raise RightsClearanceError(
            "Supplied source_assets.csv is not byte-identical to the cleared package."
        )
    try:
        package_events = load_events(root / "events.csv")
        package_sources = load_source_assets(root / "source_assets.csv")
        supplied_events = (
            tuple(events)
            if not isinstance(events, (str, Path))
            else load_events(events)
        )
        supplied_sources = (
            tuple(source_assets)
            if not isinstance(source_assets, (str, Path))
            else load_source_assets(source_assets)
        )
    except EventRegistryError as exc:
        raise RightsClearanceError(str(exc)) from exc
    package_event_rows = _normalized_registry_rows(package_events, "event_id")
    supplied_event_rows = _normalized_registry_rows(supplied_events, "event_id")
    if package_event_rows != supplied_event_rows:
        raise RightsClearanceError(
            "Supplied event registry does not exactly match the cleared package."
        )
    package_source_rows = _normalized_registry_rows(package_sources, "asset_id")
    supplied_source_rows = _normalized_registry_rows(supplied_sources, "asset_id")
    if package_source_rows != supplied_source_rows:
        raise RightsClearanceError(
            "Supplied source registry does not exactly match the cleared package."
        )
    return {
        "governance_package_id": str(seal["package_id"]),
        "governance_package_manifest_sha256": str(
            seal["package_manifest_sha256"]
        ),
        "governance_package_seal_sha256": str(seal["seal_sha256"]),
    }


def _validate_seal_safety(seal: Mapping[str, Any]) -> None:
    expected = {
        "rights_status": "approved_with_provider_conditions",
        "redistribution_status": REDISTRIBUTION_STATUS,
        "timestamp_basis": TIMESTAMP_BASIS,
        "reference_authority_assigned": False,
        "reviewers_assigned": False,
        "adjudicator_assigned": False,
        "validation_allowed": False,
        "query_model_only": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
        "seal_kind": "sha256_integrity_self_hash_not_a_digital_signature",
    }
    mismatches = [field for field, value in expected.items() if seal.get(field) != value]
    if mismatches:
        raise RightsClearanceError(
            "Cleared package seal has unsafe governance fields: "
            + ", ".join(mismatches)
        )
    _strict_utc(seal.get("decision_timestamp_utc"))
    _non_blank(seal.get("owner_name"), "seal.owner_name")
    _non_blank(seal.get("organization"), "seal.organization")
    for field in (
        "package_manifest_sha256",
        "source_pending_package_manifest_sha256",
        "seal_sha256",
    ):
        if _SHA256_RE.fullmatch(str(seal.get(field, ""))) is None:
            raise RightsClearanceError(f"Cleared package seal has invalid {field}.")


def _require_identity_consistency(
    row: Mapping[str, Any],
    decision: RightsOwnerDecision,
    *,
    label: str,
) -> None:
    expected = {
        "owner_name": decision.owner_name,
        "organization": decision.organization,
        "decision_timestamp_utc": decision.decision_timestamp_utc,
    }
    mismatches = [field for field, value in expected.items() if row.get(field) != value]
    if mismatches:
        raise RightsClearanceError(
            f"{label} does not match normalized owner identity/timestamp: "
            + ", ".join(mismatches)
        )


def _validate_source_rights_rows(
    root: Path, decision: RightsOwnerDecision
) -> None:
    fields, rows = _read_csv(root / "source_rights_decisions_v1.csv")
    if fields != _rights_fields():
        raise RightsClearanceError(
            "source_rights_decisions_v1.csv has an invalid schema."
        )
    expected_rows = {
        str(row["source_id"]): {
            field: _csv_text(row.get(field, "")) for field in fields
        }
        for row in _rights_rows(decision)
    }
    observed_rows: dict[str, dict[str, str]] = {}
    for row in rows:
        source_id = row.get("source_id", "")
        if source_id in observed_rows:
            raise RightsClearanceError(
                f"Duplicate source-rights decision for {source_id!r}."
            )
        observed_rows[source_id] = row
    if set(observed_rows) != set(expected_rows):
        raise RightsClearanceError(
            "Source-rights decisions must contain exactly the four approved "
            "sources plus the excluded MBRSC/Sentinel Asia row."
        )
    for source_id, expected in expected_rows.items():
        observed = observed_rows[source_id]
        mismatches = [field for field in fields if observed.get(field, "") != expected[field]]
        if mismatches:
            raise RightsClearanceError(
                f"Source-rights semantics changed for {source_id}: "
                + ", ".join(mismatches)
            )


def _validate_human_roles(root: Path, decision: RightsOwnerDecision) -> None:
    fields, rows = _read_csv(root / "human_role_approval_ledger.csv")
    _require_fields(
        fields,
        {
            "role_id",
            "assignee_status",
            "assignee",
            "approval_status",
            "approved_at_utc",
            "evidence_reference",
        },
        "human_role_approval_ledger.csv",
    )
    by_id: dict[str, dict[str, str]] = {}
    for row in rows:
        role_id = row.get("role_id", "")
        if role_id in by_id:
            raise RightsClearanceError(f"Duplicate human role {role_id!r}.")
        by_id[role_id] = row
    if set(by_id) != _HUMAN_ROLE_IDS:
        raise RightsClearanceError(
            "Human-role ledger must contain exactly the five required roles."
        )
    owner = by_id["RIGHTS-OWNER"]
    expected_owner = {
        "assignee_status": "assigned",
        "assignee": decision.owner_name,
        "approval_status": "self_attested_approved_with_provider_conditions",
        "approved_at_utc": decision.decision_timestamp_utc,
        "evidence_reference": "rights_owner_declaration_v1.md#self-attestation",
    }
    if any(owner.get(field) != value for field, value in expected_owner.items()):
        raise RightsClearanceError(
            "RIGHTS-OWNER role does not match the normalized owner decision."
        )
    for role_id in sorted(_HUMAN_ROLE_IDS - {"RIGHTS-OWNER"}):
        row = by_id[role_id]
        if (
            row.get("assignee_status") != "tbd"
            or row.get("assignee") != "TBD"
            or row.get("approved_at_utc") != ""
            or row.get("evidence_reference") != "none"
            or row.get("approval_status")
            not in {"not_reviewed", "not_assigned"}
        ):
            raise RightsClearanceError(
                f"Only RIGHTS-OWNER may be assigned; {role_id} must remain TBD."
            )


def _validate_cleared_registries(root: Path) -> None:
    event_fields, events = _read_csv(root / "events.csv")
    _require_fields(
        event_fields,
        {
            "label_status",
            "source_rights_status",
            "processing_allowed",
            "ml_label_derivation_allowed",
            "validation_allowed",
            "assumptions",
        },
        "events.csv",
    )
    if not events:
        raise RightsClearanceError("Cleared event registry must not be empty.")
    for row in events:
        _require_row_values(
            row,
            {
                "label_status": "rights_cleared_human_roles_tbd",
                "source_rights_status": "approved_with_provider_conditions",
                "processing_allowed": "true",
                "ml_label_derivation_allowed": "true",
                "validation_allowed": "false",
            },
            label=f"event {row.get('event_id', '<unknown>')}",
        )
        assumptions = row.get("assumptions", "").lower()
        if "accountable rights and reference approvals remain unsigned" in assumptions:
            raise RightsClearanceError(
                "Cleared event assumptions retain the stale pre-clearance rights claim."
            )

    source_fields, sources = _read_csv(root / "source_assets.csv")
    _require_fields(
        source_fields,
        {
            "license_status",
            "processing_allowed",
            "ml_label_derivation_allowed",
            "redistribution_status",
        },
        "source_assets.csv",
    )
    if not sources:
        raise RightsClearanceError("Cleared source registry must not be empty.")
    for row in sources:
        _require_row_values(
            row,
            {
                "license_status": "approved_with_provider_conditions",
                "processing_allowed": "true",
                "ml_label_derivation_allowed": "true",
                "redistribution_status": REDISTRIBUTION_STATUS.lower(),
            },
            label=f"source asset {row.get('asset_id', '<unknown>')}",
        )

    context_fields, context_rows = _read_csv(root / "aligned_context_inventory.csv")
    _require_fields(
        context_fields,
        {
            "rights_review_status",
            "processing_allowed",
            "ml_label_derivation_allowed",
            "redistribution_status",
            "query_model_only",
            "eligible_for_decision_layer",
            "eligible_for_fpps",
            "eligible_for_warning",
        },
        "aligned_context_inventory.csv",
    )
    if not context_rows:
        raise RightsClearanceError("Cleared context inventory must not be empty.")
    for row in context_rows:
        _require_row_values(
            row,
            {
                "rights_review_status": "approved_with_provider_conditions",
                "processing_allowed": "true",
                "ml_label_derivation_allowed": "true",
                "redistribution_status": REDISTRIBUTION_STATUS.lower(),
                "query_model_only": "true",
                "eligible_for_decision_layer": "false",
                "eligible_for_fpps": "false",
                "eligible_for_warning": "false",
            },
            label=f"context layer {row.get('context_layer_id', '<unknown>')}",
        )
    sensitivity = [
        row
        for row in context_rows
        if row.get("context_layer_id") == "permanent_water_context_v1_empty_sensitivity"
    ]
    if len(sensitivity) > 1:
        raise RightsClearanceError("Duplicate v1 empty-sensitivity context rows.")
    if sensitivity:
        _require_row_values(
            sensitivity[0],
            {
                "allowed_for_blinded_review_candidate": "false",
                "eligible_for_current_context_layers_csv": "false",
            },
            label="v1 empty-sensitivity context",
        )

    processed_fields, processed_rows = _read_csv(root / "processed_sar_inventory.csv")
    _require_fields(
        processed_fields,
        {
            "rights_review_status",
            "query_model_only",
            "eligible_for_decision_layer",
            "eligible_for_fpps",
            "eligible_for_warning",
        },
        "processed_sar_inventory.csv",
    )
    if not processed_rows:
        raise RightsClearanceError("Processed-SAR inventory must not be empty.")
    for row in processed_rows:
        _require_row_values(
            row,
            {
                "rights_review_status": "approved_with_provider_conditions",
                "query_model_only": "true",
                "eligible_for_decision_layer": "false",
                "eligible_for_fpps": "false",
                "eligible_for_warning": "false",
            },
            label=f"processed SAR {row.get('asset_id', '<unknown>')}",
        )


def _validate_scope_decision(root: Path, decision: RightsOwnerDecision) -> None:
    fields, rows = _read_csv(root / "pilot_scope_decisions.csv")
    _require_fields(
        fields,
        {
            "decision_id",
            "scope_status",
            "authority_type",
            "canonical_rights_effect",
            "recorded_at_utc",
            "notes",
        },
        "pilot_scope_decisions.csv",
    )
    rights_rows = [row for row in rows if row.get("decision_id") == "RIGHTS-001"]
    if len(rights_rows) != 1:
        raise RightsClearanceError(
            "pilot_scope_decisions.csv must contain exactly one RIGHTS-001 row."
        )
    _require_row_values(
        rights_rows[0],
        {
            "scope_status": "approved_with_provider_conditions",
            "authority_type": "named_data_rights_owner_self_attestation",
            "canonical_rights_effect": (
                "processing_and_ml_label_derivation_allowed_validation_not_approved"
            ),
            "recorded_at_utc": decision.decision_timestamp_utc.lower(),
        },
        label="RIGHTS-001 decision",
    )
    notes = rights_rows[0].get("notes", "")
    if "MBRSC/Sentinel Asia geometry remains excluded" not in notes:
        raise RightsClearanceError(
            "RIGHTS-001 must preserve the MBRSC/Sentinel Asia exclusion."
        )


def _validate_parent_package_binding(root: Path, seal: Mapping[str, Any]) -> None:
    parent_manifest = root / "source_pending_package_manifest.csv"
    parent_hash = _file_sha256(parent_manifest)
    if parent_hash != seal["source_pending_package_manifest_sha256"]:
        raise RightsClearanceError(
            "Source pending-package manifest does not match the package seal."
        )
    fields, rows = _read_csv(parent_manifest)
    required_fields = {
        "file_name",
        "file_size_bytes",
        "sha256",
        "artifact_role",
        "immutable_status",
    }
    if set(fields) != required_fields:
        raise RightsClearanceError("Parent pending manifest has an invalid schema.")
    parent_rows: dict[str, dict[str, str]] = {}
    for index, row in enumerate(rows, start=2):
        name = _safe_relative_name(row.get("file_name", ""), index)
        if name in parent_rows:
            raise RightsClearanceError(f"Duplicate parent pending artifact {name!r}.")
        if _SHA256_RE.fullmatch(str(row.get("sha256", ""))) is None:
            raise RightsClearanceError(f"Parent artifact {name} has invalid SHA-256.")
        try:
            if int(row.get("file_size_bytes", "")) < 0:
                raise ValueError
        except ValueError as exc:
            raise RightsClearanceError(
                f"Parent artifact {name} has invalid file size."
            ) from exc
        parent_rows[name] = row
    if set(parent_rows) != set(REQUIRED_PENDING_FILES):
        raise RightsClearanceError(
            "Parent pending manifest does not bind the exact required artifact set."
        )
    try:
        verification = json.loads(
            (root / "pending_package_verification.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise RightsClearanceError(
            f"Cannot read pending-package verification: {exc}"
        ) from exc
    if not isinstance(verification, Mapping):
        raise RightsClearanceError("Pending-package verification must be an object.")
    if (
        verification.get("verification_schema")
        != "floodguard_pending_package_verification_v1"
        or verification.get("pending_package_manifest_sha256") != parent_hash
        or verification.get("all_manifested_files_verified") is not True
        or verification.get("verified_file_count") != len(parent_rows)
    ):
        raise RightsClearanceError(
            "Pending-package verification is stale or not fully successful."
        )
    verified_files = verification.get("files")
    if not isinstance(verified_files, list):
        raise RightsClearanceError("Pending-package verification files are missing.")
    verified_by_name: dict[str, Mapping[str, Any]] = {}
    for item in verified_files:
        if not isinstance(item, Mapping):
            raise RightsClearanceError("Pending-package verification file row is invalid.")
        name = str(item.get("file_name", ""))
        if name in verified_by_name:
            raise RightsClearanceError(
                f"Duplicate pending-package verification artifact {name!r}."
            )
        verified_by_name[name] = item
    if set(verified_by_name) != set(parent_rows):
        raise RightsClearanceError(
            "Pending-package verification does not cover the parent manifest exactly."
        )
    for name, parent in parent_rows.items():
        verified = verified_by_name[name]
        expected = {
            "file_size_bytes": int(parent["file_size_bytes"]),
            "sha256": parent["sha256"],
            "artifact_role": parent["artifact_role"],
            "immutable_status": parent["immutable_status"],
        }
        if any(verified.get(field) != value for field, value in expected.items()):
            raise RightsClearanceError(
                f"Pending-package verification changed parent evidence for {name}."
            )
    for copied_name, parent_name in (
        ("prior_pending_gate_check.json", "canonical_gate_check.json"),
        ("safe_manifest_inventory.csv", "safe_manifest_inventory.csv"),
    ):
        if _file_sha256(root / copied_name) != parent_rows[parent_name]["sha256"]:
            raise RightsClearanceError(
                f"Copied parent artifact binding changed for {copied_name}."
            )


def _validate_declaration(root: Path, decision: RightsOwnerDecision) -> None:
    declaration = (root / "rights_owner_declaration_v1.md").read_text(
        encoding="utf-8"
    )
    for expected in (
        decision.owner_name,
        decision.organization,
        decision.decision_timestamp_utc,
        "YES_WITH_CONDITIONS",
        "MBRSC/Sentinel Asia external reference geometry remains excluded",
        "Validation remains disallowed",
    ):
        if expected not in declaration:
            raise RightsClearanceError(
                "Rights-owner declaration is inconsistent with the normalized decision."
            )


def _normalized_registry_rows(
    records: Sequence[EventRecord] | Sequence[SourceAssetRecord],
    key: str,
) -> list[dict[str, Any]]:
    rows = [record.as_manifest_row() for record in records]
    return sorted(rows, key=lambda row: str(row[key]))


def _require_row_values(
    row: Mapping[str, str], expected: Mapping[str, str], *, label: str
) -> None:
    mismatches = [
        field
        for field, value in expected.items()
        if str(row.get(field, "")).strip().lower() != value.lower()
    ]
    if mismatches:
        raise RightsClearanceError(
            f"Unsafe or inconsistent fields for {label}: " + ", ".join(mismatches)
        )


def _csv_text(value: Any) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    return str(value)


def _build_files(
    pending: Path,
    staging: Path,
    decision: RightsOwnerDecision,
    verification: Mapping[str, Any],
    package_id: str,
) -> None:
    _write_json(
        staging / "rights_owner_decision_input_v1.json",
        {
            "schema": DECISION_SCHEMA,
            "owner_name": decision.owner_name,
            "organization": decision.organization,
            "decision_timestamp_utc": decision.decision_timestamp_utc,
            "sources": {
                source_id: dict(decision.sources[source_id])
                for source_id in APPROVED_SOURCE_IDS
            },
        },
    )
    _write_declaration(staging / "rights_owner_declaration_v1.md", decision)
    _write_csv(
        staging / "source_rights_decisions_v1.csv",
        _rights_fields(),
        _rights_rows(decision),
    )
    _transform_events(pending / "events.csv", staging / "events.csv", decision)
    _transform_source_assets(
        pending / "source_assets.csv", staging / "source_assets.csv", decision
    )
    _transform_context(
        pending / "aligned_context_inventory.csv",
        staging / "aligned_context_inventory.csv",
        decision,
    )
    _transform_processed_sar_inventory(
        pending / "processed_sar_inventory.csv",
        staging / "processed_sar_inventory.csv",
    )
    _transform_roles(
        pending / "human_role_approval_ledger.csv",
        staging / "human_role_approval_ledger.csv",
        decision,
    )
    _transform_decisions(
        pending / "pilot_scope_decisions.csv",
        staging / "pilot_scope_decisions.csv",
        decision,
    )
    for source_name, target_name in (
        ("safe_manifest_inventory.csv", "safe_manifest_inventory.csv"),
        ("canonical_gate_check.json", "prior_pending_gate_check.json"),
        ("package_manifest.csv", "source_pending_package_manifest.csv"),
    ):
        shutil.copyfile(pending / source_name, staging / target_name)
    _write_json(staging / "pending_package_verification.json", verification)
    _write_readme(staging / "README.md", decision, verification, package_id)
    _write_output_manifest(staging)
    seal: dict[str, Any] = {
        "package_schema": PACKAGE_SCHEMA,
        "package_id": package_id,
        "owner_name": decision.owner_name,
        "organization": decision.organization,
        "decision_timestamp_utc": decision.decision_timestamp_utc,
        "timestamp_basis": TIMESTAMP_BASIS,
        "source_pending_package_manifest_sha256": verification[
            "pending_package_manifest_sha256"
        ],
        "package_manifest_sha256": _file_sha256(staging / "package_manifest.csv"),
        "rights_status": "approved_with_provider_conditions",
        "redistribution_status": REDISTRIBUTION_STATUS,
        "reference_authority_assigned": False,
        "reviewers_assigned": False,
        "adjudicator_assigned": False,
        "validation_allowed": False,
        "query_model_only": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
        "seal_kind": "sha256_integrity_self_hash_not_a_digital_signature",
    }
    seal["seal_sha256"] = _json_sha256(seal)
    _write_json(staging / "package_seal.json", seal)


def _transform_events(source: Path, target: Path, decision: RightsOwnerDecision) -> None:
    fields, rows = _read_csv(source)
    _require_fields(
        fields,
        {
            "label_status",
            "source_rights_status",
            "processing_allowed",
            "ml_label_derivation_allowed",
            "validation_allowed",
            "assumptions",
        },
        source.name,
    )
    for row in rows:
        row["label_status"] = "rights_cleared_human_roles_tbd"
        row["source_rights_status"] = "approved_with_provider_conditions"
        row["processing_allowed"] = "true"
        row["ml_label_derivation_allowed"] = "true"
        row["validation_allowed"] = "false"
        assumptions = row["assumptions"].replace(
            "Technical processing exists but accountable rights and reference "
            "approvals remain unsigned.",
            "Technical processing and accountable source-rights approval are "
            "recorded; reference authority and reviewer approvals remain unsigned.",
        )
        row["assumptions"] = _replace_or_append(
            assumptions,
            "Rights owner is TBD.",
            "Rights owner self-attestation is recorded with provider conditions. "
            "Reference authority, reviewers, adjudicator, and validation remain "
            "unapproved.",
        )
    _write_csv(target, fields, rows)


def _transform_source_assets(
    source: Path, target: Path, decision: RightsOwnerDecision
) -> None:
    fields, rows = _read_csv(source)
    _require_fields(
        fields,
        {
            "license_status",
            "processing_allowed",
            "ml_label_derivation_allowed",
            "redistribution_status",
            "assumptions",
        },
        source.name,
    )
    for row in rows:
        row["license_status"] = "approved_with_provider_conditions"
        row["processing_allowed"] = "true"
        row["ml_label_derivation_allowed"] = "true"
        row["redistribution_status"] = REDISTRIBUTION_STATUS
        row["assumptions"] = _replace_or_append(
            row["assumptions"],
            "Rights owner is TBD.",
            f"Rights owner: {decision.owner_name}, {decision.organization}. "
            f"Raw notice: {SENTINEL_RAW_NOTICE}. Modified notice: "
            f"{SENTINEL_MODIFIED_NOTICE}. Redistribution is conditional, not an "
            "unrestricted relicensing grant.",
        )
    _write_csv(target, fields, rows)


def _transform_context(
    source: Path, target: Path, decision: RightsOwnerDecision
) -> None:
    fields, rows = _read_csv(source)
    _require_fields(
        fields,
        {
            "context_layer_id",
            "source_roles",
            "allowed_for_blinded_review_candidate",
            "eligible_for_current_context_layers_csv",
            "rights_review_status",
            "processing_allowed",
            "ml_label_derivation_allowed",
            "redistribution_status",
            "query_model_only",
            "eligible_for_decision_layer",
            "eligible_for_fpps",
            "eligible_for_warning",
            "assumptions",
        },
        source.name,
    )
    for row in rows:
        roles = row["source_roles"].lower()
        if not any(token in roles for token in ("worldcover", "jrc_", "copernicus_dem")):
            raise RightsClearanceError(
                f"Unrecognized context source_roles {row['source_roles']!r}."
            )
        original_safety = {
            field: row[field]
            for field in (
                "allowed_for_blinded_review_candidate",
                "eligible_for_current_context_layers_csv",
                "query_model_only",
                "eligible_for_decision_layer",
                "eligible_for_fpps",
                "eligible_for_warning",
            )
        }
        row["rights_review_status"] = "approved_with_provider_conditions"
        row["processing_allowed"] = "true"
        row["ml_label_derivation_allowed"] = "true"
        row["redistribution_status"] = REDISTRIBUTION_STATUS
        row["assumptions"] = (
            row["assumptions"].rstrip()
            + " Rights clearance changes permitted use only; this remains static "
            "reviewer context, not flood truth, validation truth, FPPS input, or a "
            "warning layer. Provider attribution conditions apply."
        )
        for field, expected in original_safety.items():
            if row[field] != expected:
                raise RightsClearanceError(f"Context transformation altered {field}.")
        if row["context_layer_id"] == "permanent_water_context_v1_empty_sensitivity":
            if (
                row["allowed_for_blinded_review_candidate"].lower() != "false"
                or row["eligible_for_current_context_layers_csv"].lower() != "false"
            ):
                raise RightsClearanceError(
                    "v1 empty sensitivity row must remain excluded from review and "
                    "the current context layer list."
                )
    _write_csv(target, fields, rows)


def _transform_processed_sar_inventory(source: Path, target: Path) -> None:
    """Clear governance status without changing technical or safety facts."""

    fields, rows = _read_csv(source)
    _require_fields(
        fields,
        {
            "rights_review_status",
            "query_model_only",
            "eligible_for_decision_layer",
            "eligible_for_fpps",
            "eligible_for_warning",
            "assumptions",
        },
        source.name,
    )
    for row in rows:
        original_safety = {
            field: row[field]
            for field in (
                "query_model_only",
                "eligible_for_decision_layer",
                "eligible_for_fpps",
                "eligible_for_warning",
            )
        }
        row["rights_review_status"] = "approved_with_provider_conditions"
        row["assumptions"] = (
            row["assumptions"].rstrip()
            + " Rights use is cleared under the source-specific provider conditions "
            "in source_rights_decisions_v1.csv; this does not change the technical "
            "processing evidence or make the raster flood truth."
        )
        for field, expected in original_safety.items():
            if row[field] != expected:
                raise RightsClearanceError(
                    f"Processed-SAR transformation altered safety field {field}."
                )
    _write_csv(target, fields, rows)


def _transform_roles(source: Path, target: Path, decision: RightsOwnerDecision) -> None:
    fields, rows = _read_csv(source)
    _require_fields(
        fields,
        {
            "role_id",
            "assignee_status",
            "assignee",
            "approval_status",
            "approved_at_utc",
            "evidence_reference",
            "blocking_stage",
            "blocker",
            "next_action",
        },
        source.name,
    )
    found = False
    for row in rows:
        if row["role_id"] == "RIGHTS-OWNER":
            found = True
            row["assignee_status"] = "assigned"
            row["assignee"] = decision.owner_name
            row["approval_status"] = "self_attested_approved_with_provider_conditions"
            row["approved_at_utc"] = decision.decision_timestamp_utc
            row["evidence_reference"] = (
                "rights_owner_declaration_v1.md#self-attestation"
            )
            row["blocking_stage"] = "none"
            row["blocker"] = (
                "Rights gate cleared under recorded provider conditions; this does "
                "not approve validation or human scientific roles."
            )
            row["next_action"] = (
                "Assign an independent reference authority and define a real "
                "rights-cleared calibration reference."
            )
        else:
            if row["assignee"] != "TBD" or row["assignee_status"] != "tbd":
                raise RightsClearanceError(
                    f"Only RIGHTS-OWNER may be assigned; {row['role_id']} is not TBD."
                )
    if not found:
        raise RightsClearanceError("Human-role ledger has no RIGHTS-OWNER row.")
    _write_csv(target, fields, rows)


def _transform_decisions(
    source: Path, target: Path, decision: RightsOwnerDecision
) -> None:
    fields, rows = _read_csv(source)
    _require_fields(
        fields,
        {
            "decision_id",
            "decision",
            "scope_status",
            "authority_type",
            "canonical_rights_effect",
            "recorded_at_utc",
            "notes",
        },
        source.name,
    )
    if any(row["decision_id"] == "RIGHTS-001" for row in rows):
        raise RightsClearanceError("pilot_scope_decisions.csv already has RIGHTS-001.")
    rows.append(
        {
            "decision_id": "RIGHTS-001",
            "decision": (
                "Self-attested conditional approval for Sentinel-1, JRC Global "
                "Surface Water, ESA WorldCover 2021, and Copernicus DEM GLO-30"
            ),
            "scope_status": "approved_with_provider_conditions",
            "authority_type": "named_data_rights_owner_self_attestation",
            "canonical_rights_effect": (
                "processing_and_ml_label_derivation_allowed_validation_not_approved"
            ),
            "recorded_at_utc": decision.decision_timestamp_utc,
            "notes": (
                "All requested redistribution is YES_WITH_CONDITIONS. Provider "
                "notices remain mandatory. MBRSC/Sentinel Asia geometry remains "
                "excluded. Timestamp is user-declared UTC and was not "
                "independently clock-verified."
            ),
        }
    )
    _write_csv(target, fields, rows)


def _rights_fields() -> list[str]:
    return [
        "decision_id",
        "source_id",
        "source_name",
        "owner_name",
        "organization",
        "decision_timestamp_utc",
        "timestamp_basis",
        "local_processing",
        "ml_label_derivation",
        "blinded_reviewer_display",
        "redistribution_requested",
        "redistribution_status",
        "rights_status",
        "official_terms_url",
        "license_or_terms",
        "raw_attribution_notice",
        "modified_attribution_notice",
        "publication_citation",
        "mandatory_conditions",
        "validation_allowed",
        "safety_notes",
    ]


def _rights_rows(decision: RightsOwnerDecision) -> list[dict[str, Any]]:
    common = {
        "owner_name": decision.owner_name,
        "organization": decision.organization,
        "decision_timestamp_utc": decision.decision_timestamp_utc,
        "timestamp_basis": TIMESTAMP_BASIS,
        "local_processing": True,
        "ml_label_derivation": True,
        "blinded_reviewer_display": True,
        "redistribution_requested": True,
        "redistribution_status": REDISTRIBUTION_STATUS,
        "rights_status": "approved_with_provider_conditions",
        "validation_allowed": False,
        "safety_notes": (
            "Use permission is not scientific validation. Query/reviewer context "
            "only; not flood truth, FPPS input, decision layer, or warning."
        ),
    }
    rows = [
        {
            **common,
            "decision_id": "RIGHTS-SENTINEL1-001",
            "source_id": "sentinel1",
            "source_name": "Copernicus Sentinel-1 GRD",
            "official_terms_url": (
                "https://sentinels.copernicus.eu/documents/247904/690755/"
                "Sentinel_Data_Legal_Notice"
            ),
            "license_or_terms": "Copernicus Sentinel Data Legal Notice",
            "raw_attribution_notice": SENTINEL_RAW_NOTICE,
            "modified_attribution_notice": SENTINEL_MODIFIED_NOTICE,
            "publication_citation": "Use the applicable Sentinel notice with year 2024.",
            "mandatory_conditions": (
                "Use the raw notice for unmodified Sentinel data and the modified "
                "notice for derived RTC, change features, previews, labels, or "
                "models that contain adapted Sentinel data. This approval covers "
                "Sentinel product data and TeamBits derivatives, not unrelated CDSE "
                "portal content. Do not imply official Copernicus endorsement."
            ),
        },
        {
            **common,
            "decision_id": "RIGHTS-JRC-GSW-001",
            "source_id": "jrc_global_surface_water",
            "source_name": "JRC Global Surface Water v1.4",
            "official_terms_url": "https://global-surface-water.appspot.com/download",
            "license_or_terms": "Copernicus Programme free use with acknowledgement",
            "raw_attribution_notice": JRC_ATTRIBUTION,
            "modified_attribution_notice": JRC_ATTRIBUTION,
            "publication_citation": JRC_CITATION,
            "mandatory_conditions": (
                "Published maps must show 'Source: EC JRC/Google'. Publications, "
                "models, and data products must acknowledge the dataset and cite "
                "Pekel et al. with DOI 10.1038/nature20584. The official access page "
                "reports v1.4 occurrence-processing inconsistencies and a seasonality "
                "issue that can overestimate seasonal water; retain v1.4 as versioned "
                "reviewer context and run a separately versioned v1.5 sensitivity "
                "check before release-grade multi-event use."
            ),
        },
        {
            **common,
            "decision_id": "RIGHTS-WORLDCOVER-001",
            "source_id": "esa_worldcover_2021",
            "source_name": "ESA WorldCover 10 m 2021 v200",
            "official_terms_url": "https://esa-worldcover.org/en/data-access",
            "license_or_terms": "Creative Commons Attribution 4.0 International",
            "raw_attribution_notice": WORLDCOVER_ATTRIBUTION,
            "modified_attribution_notice": WORLDCOVER_ATTRIBUTION,
            "publication_citation": WORLDCOVER_CITATION,
            "mandatory_conditions": (
                "Retain the official WorldCover attribution; cite WorldCover 2021 "
                "v200 and DOI 10.5281/zenodo.7254221; link or name CC BY 4.0; "
                "identify modifications and do not imply endorsement."
            ),
        },
        {
            **common,
            "decision_id": "RIGHTS-COPDEM-001",
            "source_id": "copernicus_dem_glo30",
            "source_name": "Copernicus DEM GLO-30 / WorldDEM-30",
            "official_terms_url": (
                "https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/"
                "Data/DEM/resources/license/License-COPDEM-30.pdf"
            ),
            "license_or_terms": "Licence for Copernicus WorldDEM-30",
            "raw_attribution_notice": COPDEM_RAW_NOTICE,
            "modified_attribution_notice": COPDEM_MODIFIED_NOTICE,
            "publication_citation": "https://doi.org/10.5270/ESA-c5d3d65",
            "mandatory_conditions": (
                f"For distribution or public communication include the applicable "
                f"raw or modified notice and this Article 6(c) sentence: "
                f"'{COPDEM_ARTICLE_6C_NOTICE}'. Do not imply provider, licensor, "
                "ESA, EU, or Copernicus endorsement; bind downstream redistributors "
                "to the same obligations. This approval covers the identified public "
                "COP-DEM GLO-30-F asset only, not EEA-10 or other restricted products."
            ),
        },
        {
            "decision_id": "RIGHTS-MBRSC-SENTINEL-ASIA-001",
            "source_id": "mbrsc_sentinel_asia_reference",
            "source_name": "MBRSC / Sentinel Asia external reference geometry",
            "owner_name": decision.owner_name,
            "organization": decision.organization,
            "decision_timestamp_utc": decision.decision_timestamp_utc,
            "timestamp_basis": TIMESTAMP_BASIS,
            "local_processing": False,
            "ml_label_derivation": False,
            "blinded_reviewer_display": False,
            "redistribution_requested": False,
            "redistribution_status": "NO_PERMISSION_NOT_CLEARED",
            "rights_status": "excluded_pending_separate_permission",
            "official_terms_url": "https://sentinel-asia.org/",
            "license_or_terms": "Not assessed; separate permission required",
            "raw_attribution_notice": "",
            "modified_attribution_notice": "",
            "publication_citation": "",
            "mandatory_conditions": (
                "Do not ingest, copy, rasterize, derive labels from, display, "
                "redistribute, or validate against the geometry until written "
                "permission and its conditions are recorded in a new package."
            ),
            "validation_allowed": False,
            "safety_notes": "No MBRSC/Sentinel Asia geometry is registered here.",
        },
    ]
    return rows


def _write_declaration(path: Path, decision: RightsOwnerDecision) -> None:
    approvals = "\n".join(
        f"- {source_id}: local processing YES; ML-label derivation YES; blinded "
        "reviewer display YES; redistribution YES_WITH_CONDITIONS."
        for source_id in APPROVED_SOURCE_IDS
    )
    path.write_text(
        f"""# Data-rights owner self-attestation

## Self-attestation

I, **{decision.owner_name}**, acting for **{decision.organization}**, record the
following project-use decision at **{decision.decision_timestamp_utc}**:

{approvals}

The timestamp above is preserved exactly as user-declared UTC. It was accepted
without independent clock or identity verification.

Every redistribution approval means **YES_WITH_CONDITIONS**, not unrestricted
ownership, sublicensing, or removal of provider notices. The source-specific
notices and conditions in `source_rights_decisions_v1.csv` remain mandatory.

MBRSC/Sentinel Asia external reference geometry remains excluded until separate
written permission is cleared and recorded.

## Boundaries of this declaration

This document is an accountable internal self-attestation and the evidence
reference for the FloodGuard rights gate. It is not legal advice, a provider's
licence, identity verification, scientific validation, flood truth, or an
operational flood-detection approval. It does not assign a reference authority,
Reviewer A, Reviewer B, or Adjudicator C. Validation remains disallowed.
""",
        encoding="utf-8",
        newline="\n",
    )


def _write_readme(
    path: Path,
    decision: RightsOwnerDecision,
    verification: Mapping[str, Any],
    package_id: str,
) -> None:
    path.write_text(
        f"""# Mae Sai governance clearance package {package_id}

This immutable package records the self-attested data-use decision of
**{decision.owner_name}** for **{decision.organization}**, declared at
**{decision.decision_timestamp_utc}** UTC.

## What this package clears

- Local processing, ML-label derivation, and blinded reviewer display for the
  four named open-data sources.
- Redistribution only as `YES_WITH_CONDITIONS`, with the exact provider notices
  in `source_rights_decisions_v1.csv`.
- Generation of the code-backed processing/alignment receipt after the
  downstream registry validates this package.

## What remains blocked

- Reference authority: TBD.
- Calibration reference: absent.
- Reviewer A and Reviewer B: TBD.
- Adjudicator C: TBD.
- Calibration, formal labels, consensus, release QA, training, and validation.
- Any FPPS, decision-layer, warning, or operational flood-detection use.
- Any MBRSC/Sentinel Asia geometry use.

## Integrity model

The source pending manifest and all {verification['verified_file_count']}
manifested pending artifacts were byte-size and SHA-256 verified before this
package was constructed. `pending_package_verification.json` records those
checks. `package_manifest.csv` hashes every content artifact. `package_seal.json`
hashes that manifest and contains a canonical self-hash. This is tamper evidence,
not a digital signature or independent identity verification.

## Important files

- `rights_owner_declaration_v1.md`: the owner-created evidence path requested by
  the project.
- `rights_owner_decision_input_v1.json`: normalized machine-readable source
  declaration captured from the direct user instruction.
- `source_rights_decisions_v1.csv`: source-by-source conditions and official
  terms URLs.
- `events.csv`, `source_assets.csv`, `aligned_context_inventory.csv`: cleared
  registries; validation remains false and context remains non-truth.
- `human_role_approval_ledger.csv`: only the rights owner is assigned.
- `pilot_scope_decisions.csv`: original scope plus `RIGHTS-001`.
- `safe_manifest_inventory.csv`: unchanged source provenance.
- `processed_sar_inventory.csv`: unchanged technical provenance with its rights
  review status advanced under this package; all safety flags remain unchanged.
- `prior_pending_gate_check.json`: historical evidence of the earlier block;
  it is not the current gate result.

## Next human gate

Appoint a qualified reference authority and define a rights-cleared calibration
reference. A solo beginner must not fill the independent Reviewer A, Reviewer B,
and Adjudicator C roles with one identity and call the result independent
validation. Solo practice annotations are useful for learning, but they remain
practice-only until externally reviewed.
""",
        encoding="utf-8",
        newline="\n",
    )


def _write_output_manifest(root: Path) -> None:
    rows: list[dict[str, Any]] = []
    for name in sorted(CLEARED_CONTENT_ROLES):
        artifact = root / name
        if not artifact.is_file():
            raise RightsClearanceError(f"Expected output artifact is absent: {name}")
        rows.append(
            {
                "file_name": name,
                "file_size_bytes": artifact.stat().st_size,
                "sha256": _file_sha256(artifact),
                "artifact_role": CLEARED_CONTENT_ROLES[name],
                "immutable_status": "frozen_cleared_v1",
            }
        )
    _write_csv(
        root / "package_manifest.csv",
        [
            "file_name",
            "file_size_bytes",
            "sha256",
            "artifact_role",
            "immutable_status",
        ],
        rows,
    )


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise RightsClearanceError(f"CSV has no header: {path}")
            fields = list(reader.fieldnames)
            rows = [dict(row) for row in reader]
    except OSError as exc:
        raise RightsClearanceError(f"Cannot read CSV {path}: {exc}") from exc
    if len(fields) != len(set(fields)):
        raise RightsClearanceError(f"CSV has duplicate columns: {path}")
    return fields, rows


def _write_csv(path: Path, fields: list[str], rows: list[Mapping[str, Any]]) -> None:
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _require_fields(fields: list[str], required: set[str], source: str) -> None:
    missing = sorted(required - set(fields))
    if missing:
        raise RightsClearanceError(f"{source} lacks required columns: {missing}.")


def _non_blank(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RightsClearanceError(f"{field} must be a non-blank string.")
    return value.strip()


def _strict_utc(value: Any) -> str:
    if not isinstance(value, str) or not _UTC_RE.fullmatch(value):
        raise RightsClearanceError(
            "decision_timestamp_utc must use exact YYYY-MM-DDTHH:MM:SSZ format."
        )
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise RightsClearanceError("decision_timestamp_utc is not a real UTC time.") from exc
    return value


def _safe_relative_name(value: str, row_number: int) -> str:
    name = value.strip()
    pure = PurePosixPath(name.replace("\\", "/"))
    if (
        not name
        or pure.is_absolute()
        or len(pure.parts) != 1
        or pure.name in {".", ".."}
        or ":" in pure.name
    ):
        raise RightsClearanceError(
            f"Pending package manifest row {row_number} has unsafe file_name {name!r}."
        )
    return pure.name


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_sha256(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def _replace_or_append(original: str, old: str, replacement: str) -> str:
    text = original.rstrip()
    if old in text:
        return text.replace(old, replacement)
    return f"{text} {replacement}".strip()
