"""Fail-closed, immutable human-role evidence packages.

This module validates attributable *local evidence* for the people assigned to
the label-factory review workflow.  It deliberately separates public candidate
research from an accepted appointment.  Even a valid package proves only that
the supplied bytes, declarations, terms, and identifiers are internally
consistent; it does not independently verify a person's identity, expertise,
independence, or conduct.

Formal review can be authorized only when the exact Reviewer A and Reviewer B
role identifiers appear in a cryptographically valid, passing calibration
receipt.  The package itself is never training data and is never eligible for
the FloodGuard decision layer, FPPS, or warnings.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from typing import Any

from floodguard.label_factory.calibration import (
    ReviewerCalibrationError,
    load_reviewer_calibration_receipt,
)


REQUEST_SCHEMA = "floodguard.human_role_package_request.v1"
PACKAGE_SCHEMA = "floodguard.human_role_package.v1"
ROLE_EVIDENCE_LIMITATION = (
    "This package verifies local file presence, declared attribution, checksums, "
    "timestamps, role separation, and recorded decisions only. It does not "
    "independently verify legal identity, qualifications, independence, blinding "
    "conduct, or review competence; public research and self-entered strings are "
    "not certification."
)
IDENTITY_STATUS = "not_independently_verified_by_software"
QUALIFICATION_STATUS = "documented_basis_not_certified_by_software"
LOCAL_EVIDENCE_STATUS = "local_copy_hash_verified_only"

ROLE_CATEGORIES = (
    "reference_authority",
    "reviewer_a",
    "reviewer_b",
    "adjudicator_c",
)
ROLE_ID_PATTERNS = {
    "reference_authority": re.compile(r"FG-RA-[0-9]{3,}"),
    "reviewer_a": re.compile(r"FG-RV-A-[0-9]{3,}"),
    "reviewer_b": re.compile(r"FG-RV-B-[0-9]{3,}"),
    "adjudicator_c": re.compile(r"FG-ADJ-C-[0-9]{3,}"),
}
EVIDENCE_TYPES = frozenset(
    {
        "role_acceptance",
        "conflict_disclosure_and_decision",
        "participant_data_use_terms",
        "qualification_basis",
        "independence_mitigation_approval",
    }
)
PARTICIPATION_MODES = frozenset({"volunteer", "paid_by_time"})
ANNOTATION_USE_SCOPES = frozenset(
    {"internal_research_only", "potentially_publishable_with_explicit_terms"}
)
CONFLICT_DECISIONS = frozenset(
    {"no_conflict_declared", "managed_with_controls", "accepted_with_controls"}
)
REVIEW_LANES = frozenset(
    {
        "independent_blinded",
        "authority_approved_mitigated_non_independent",
        "authority_role_not_blinded",
    }
)

_UTC_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_SHA_RE = re.compile(r"[0-9a-f]{64}")
_PERSON_ID_RE = re.compile(r"FG-HUM-[0-9]{3,}")
_CANDIDATE_ID_RE = re.compile(r"FG-CAND-(?:(?:B|RA)-)?[0-9]{3,}")
_EVIDENCE_ID_RE = re.compile(r"FG-EV-[0-9]{3,}")
_PACKAGE_NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]*")

_REQUEST_KEYS = frozenset(
    {
        "schema",
        "package_name",
        "version",
        "event_id",
        "protocol_version",
        "taxonomy_version",
        "created_at_utc",
        "created_by_person_id",
        "participation_mode",
        "annotation_use_scope",
        "public_release_requires_separate_project_decision",
        "reference_authority_adjudicator_dual_role_allowed",
        "candidate_research",
        "appointments",
        "evidence",
        "formal_review_authorization_requested",
        "calibration_receipt_file_sha256",
        "assumptions",
    }
)
_CANDIDATE_KEYS = frozenset(
    {
        "candidate_id",
        "display_name",
        "source_reference",
        "researched_at_utc",
        "candidate_role_categories",
        "research_status",
    }
)
_EVIDENCE_KEYS = frozenset(
    {
        "evidence_id",
        "evidence_type",
        "role_id",
        "person_id",
        "local_path",
        "sha256",
        "captured_at_utc",
        "attributable_sender",
        "attributable_recipient",
        "verification_status",
    }
)
_APPOINTMENT_KEYS = frozenset(
    {
        "role_id",
        "role_category",
        "person_id",
        "appointment_status",
        "accepted_at_utc",
        "acceptance_evidence_id",
        "conflict_declared",
        "conflict_decision",
        "conflict_controls",
        "conflict_decided_by_person_id",
        "conflict_decided_at_utc",
        "conflict_evidence_id",
        "data_terms_accepted_at_utc",
        "data_terms_evidence_id",
        "annotation_use_scope",
        "public_release_permission",
        "retention_end_utc",
        "withdrawal_terms",
        "compensation_basis",
        "qualification_summary",
        "qualification_evidence_id",
        "project_operator",
        "prior_prohibited_evidence_exposure",
        "review_lane",
        "independence_controls",
        "independence_approved_by_role_id",
        "independence_decision_evidence_id",
    }
)
_NORMALIZED_CANDIDATE_KEYS = frozenset(
    set(_CANDIDATE_KEYS)
    | {
        "confers_nomination",
        "confers_acceptance",
        "confers_identity_verification",
        "confers_qualification_certification",
    }
)
_NORMALIZED_EVIDENCE_KEYS = frozenset(
    (set(_EVIDENCE_KEYS) - {"local_path"}) | {"package_path"}
)
_NORMALIZED_APPOINTMENT_KEYS = frozenset(
    set(_APPOINTMENT_KEYS) | {"identity_status", "qualification_status"}
)
_CALIBRATION_BINDING_KEYS = frozenset(
    {
        "package_path",
        "file_sha256",
        "receipt_sha256",
        "reviewer_ids",
        "protocol_version",
        "taxonomy_version",
        "calibration_completed_at_utc",
        "formal_review_not_before_utc",
        "calibration_passed",
    }
)
_PACKAGE_KEYS = frozenset(
    {
        "artifact_schema",
        "request_schema",
        "package_name",
        "version",
        "package_id",
        "parent_package_id",
        "parent_manifest_sha256",
        "event_id",
        "protocol_version",
        "taxonomy_version",
        "created_at_utc",
        "created_by_person_id",
        "participation_mode",
        "annotation_use_scope",
        "public_release_requires_separate_project_decision",
        "reference_authority_adjudicator_dual_role_allowed",
        "candidate_research",
        "appointments",
        "evidence",
        "formal_review_authorization_requested",
        "calibration_receipt_file_sha256",
        "calibration_receipt",
        "formal_review_authorized",
        "formal_review_authorized_from_utc",
        "package_status",
        "assumptions",
        "role_evidence_limitation",
        "identity_verification_status",
        "qualification_verification_status",
        "genuinely_blinded_double_review",
        "eligible_for_model_training",
        "eligible_for_query_model_training",
        "eligible_for_decision_layer",
        "eligible_for_fpps",
        "eligible_for_warning",
        "manifest_sha256",
    }
)


class HumanRolePackageError(ValueError):
    """Raised when human-role evidence is incomplete, unsafe, or inconsistent."""


def load_human_role_request(path: str | Path) -> dict[str, Any]:
    """Load and strictly validate a human-role package request JSON."""

    payload = _load_json_object(Path(path), "human-role package request")
    _require_exact_keys(payload, _REQUEST_KEYS, "human-role package request")
    if payload.get("schema") != REQUEST_SCHEMA:
        raise HumanRolePackageError(f"Request schema must be exactly {REQUEST_SCHEMA!r}.")
    # Full relational validation needs evidence-root paths and happens in build.
    return dict(payload)


def build_human_role_package(
    request: Mapping[str, Any] | str | Path,
    *,
    evidence_root: str | Path,
    output_dir: str | Path,
    calibration_receipt_path: str | Path | None = None,
    parent_package: str | Path | None = None,
) -> Path:
    """Validate, copy, hash, and freeze a versioned human-role package once.

    ``human_coordination_v2`` planning files are not accepted as appointment
    evidence merely because they exist.  Every appointment must reference
    attributable evidence rows whose local files exist below ``evidence_root``
    and match their declared SHA-256 values.
    """

    payload = (
        load_human_role_request(request)
        if isinstance(request, (str, Path))
        else _copy_mapping(request, "human-role package request")
    )
    _require_exact_keys(payload, _REQUEST_KEYS, "human-role package request")
    if payload.get("schema") != REQUEST_SCHEMA:
        raise HumanRolePackageError(f"Request schema must be exactly {REQUEST_SCHEMA!r}.")

    root = Path(evidence_root).resolve()
    if not root.is_dir():
        raise HumanRolePackageError(f"Evidence root is not a directory: {root}")
    normalized = _validate_request(payload, root)

    parent_manifest: dict[str, Any] | None = None
    if parent_package is not None:
        parent_manifest = validate_human_role_package(parent_package)
    _validate_version_lineage(normalized, parent_manifest)

    receipt_source = Path(calibration_receipt_path).resolve() if calibration_receipt_path else None
    receipt_binding = _validate_calibration_binding(normalized, receipt_source)
    normalized["calibration_receipt"] = receipt_binding
    normalized["formal_review_authorized"] = bool(
        normalized["formal_review_authorization_requested"] and receipt_binding
    )
    normalized["formal_review_authorized_from_utc"] = (
        receipt_binding["formal_review_not_before_utc"]
        if normalized["formal_review_authorized"]
        else None
    )
    genuinely_blinded = _is_genuinely_blinded_double_review(
        normalized["appointments"]
    )
    normalized["package_status"] = (
        (
            "formal_review_gate_open_independent_a_b"
            if genuinely_blinded
            else "formal_review_gate_open_mitigated_non_independent_a"
        )
        if normalized["formal_review_authorized"]
        else "formal_review_hold_calibration_or_owner_authorization_pending"
    )
    normalized["parent_package_id"] = (
        parent_manifest["package_id"] if parent_manifest else None
    )
    normalized["parent_manifest_sha256"] = (
        parent_manifest["manifest_sha256"] if parent_manifest else None
    )

    target = Path(output_dir)
    target_parent = target.parent.resolve()
    target_parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise HumanRolePackageError(
            f"Human-role package already exists and cannot be overwritten: {target}"
        )

    temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}.tmp-", dir=target_parent))
    try:
        evidence_dir = temporary / "evidence"
        evidence_dir.mkdir()
        copied_evidence: list[dict[str, Any]] = []
        for row in normalized.pop("_evidence_sources"):
            source = Path(row.pop("_resolved_source"))
            suffix = source.suffix.lower()
            package_name = f"{row['evidence_id']}{suffix}"
            destination = evidence_dir / package_name
            with source.open("rb") as source_handle, destination.open("xb") as target_handle:
                shutil.copyfileobj(source_handle, target_handle)
                target_handle.flush()
                os.fsync(target_handle.fileno())
            if _file_sha256(destination) != row["sha256"]:
                raise HumanRolePackageError(
                    f"Evidence changed while being copied: {row['evidence_id']}"
                )
            row["package_path"] = f"evidence/{package_name}"
            copied_evidence.append(row)
        normalized["evidence"] = copied_evidence

        if receipt_source is not None:
            calibration_dir = temporary / "calibration"
            calibration_dir.mkdir()
            destination = calibration_dir / "reviewer_calibration_receipt.json"
            with receipt_source.open("rb") as source_handle, destination.open("xb") as target_handle:
                shutil.copyfileobj(source_handle, target_handle)
                target_handle.flush()
                os.fsync(target_handle.fileno())
            if _file_sha256(destination) != receipt_binding["file_sha256"]:
                raise HumanRolePackageError("Calibration receipt changed while being copied.")

        manifest_unsigned = {
            "artifact_schema": PACKAGE_SCHEMA,
            **normalized,
            "role_evidence_limitation": ROLE_EVIDENCE_LIMITATION,
            "identity_verification_status": IDENTITY_STATUS,
            "qualification_verification_status": QUALIFICATION_STATUS,
            "genuinely_blinded_double_review": genuinely_blinded,
            "eligible_for_model_training": False,
            "eligible_for_query_model_training": False,
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
        }
        manifest = dict(manifest_unsigned)
        manifest["manifest_sha256"] = _canonical_json_sha256(manifest_unsigned)
        manifest_path = temporary / "human_role_package.json"
        with manifest_path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

        # Validate the exact bytes before making the directory visible.
        validate_human_role_package(temporary)
        try:
            temporary.rename(target)
        except FileExistsError as exc:
            raise HumanRolePackageError(
                f"Human-role package already exists and cannot be overwritten: {target}"
            ) from exc
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return target


def validate_human_role_package(path: str | Path) -> dict[str, Any]:
    """Verify a frozen package, its self-hash, evidence, and calibration gate."""

    root = Path(path)
    manifest_path = root / "human_role_package.json"
    payload = _load_json_object(manifest_path, "human-role package")
    _require_exact_keys(payload, _PACKAGE_KEYS, "human-role package")
    if payload.get("artifact_schema") != PACKAGE_SCHEMA:
        raise HumanRolePackageError(f"Package schema must be exactly {PACKAGE_SCHEMA!r}.")
    digest = _required_sha(payload.get("manifest_sha256"), "manifest_sha256")
    unsigned = dict(payload)
    unsigned.pop("manifest_sha256", None)
    if _canonical_json_sha256(unsigned) != digest:
        raise HumanRolePackageError("Human-role package self-hash does not match its content.")

    if payload.get("request_schema") != REQUEST_SCHEMA:
        raise HumanRolePackageError("Human-role package request schema is unsupported.")
    package_name = _required_match(payload.get("package_name"), _PACKAGE_NAME_RE, "package_name")
    version = payload.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise HumanRolePackageError("Package version must be a positive integer.")
    if payload.get("package_id") != f"{package_name}_v{version}":
        raise HumanRolePackageError("package_id does not match package_name and version.")
    parent_id = payload.get("parent_package_id")
    parent_sha = payload.get("parent_manifest_sha256")
    if version == 1:
        if parent_id is not None or parent_sha is not None:
            raise HumanRolePackageError("Version 1 must not declare parent lineage.")
    else:
        _required_text(parent_id, "parent_package_id")
        _required_sha(parent_sha, "parent_manifest_sha256")
    _required_text(payload.get("event_id"), "event_id")
    _required_text(payload.get("protocol_version"), "protocol_version")
    _required_text(payload.get("taxonomy_version"), "taxonomy_version")
    _required_match(payload.get("created_by_person_id"), _PERSON_ID_RE, "created_by_person_id")
    _required_text(payload.get("assumptions"), "assumptions")
    _created_text, package_created = _strict_utc(payload.get("created_at_utc"), "created_at_utc")
    participation = _required_choice(
        payload.get("participation_mode"), PARTICIPATION_MODES, "participation_mode"
    )
    use_scope = _required_choice(
        payload.get("annotation_use_scope"), ANNOTATION_USE_SCOPES, "annotation_use_scope"
    )
    if payload.get("public_release_requires_separate_project_decision") is not True:
        raise HumanRolePackageError(
            "public_release_requires_separate_project_decision must remain true."
        )

    candidates = _require_sequence(payload.get("candidate_research"), "candidate_research")
    candidate_ids: set[str] = set()
    for index, item in enumerate(candidates):
        row = _copy_mapping(item, f"candidate_research[{index}]")
        _require_exact_keys(row, _NORMALIZED_CANDIDATE_KEYS, f"candidate_research[{index}]")
        candidate_id = _required_match(row.get("candidate_id"), _CANDIDATE_ID_RE, "candidate_id")
        if candidate_id in candidate_ids:
            raise HumanRolePackageError(f"Duplicate candidate_id: {candidate_id}")
        candidate_ids.add(candidate_id)
        _required_text(row.get("display_name"), "display_name")
        _required_text(row.get("source_reference"), "source_reference")
        _researched_text, researched = _strict_utc(
            row.get("researched_at_utc"), "researched_at_utc"
        )
        if researched > package_created:
            raise HumanRolePackageError(f"Candidate {candidate_id} was researched after package creation.")
        categories = _require_sequence(
            row.get("candidate_role_categories"), "candidate_role_categories"
        )
        if not categories or len(categories) != len(set(categories)):
            raise HumanRolePackageError(
                f"Candidate {candidate_id} needs unique role categories."
            )
        for category in categories:
            _required_choice(category, frozenset(ROLE_CATEGORIES), "candidate_role_category")
        if row.get("research_status") != "public_research_only_not_nominated_or_accepted":
            raise HumanRolePackageError(f"Candidate {candidate_id} is not marked research-only.")
        for field in (
            "confers_nomination",
            "confers_acceptance",
            "confers_identity_verification",
            "confers_qualification_certification",
        ):
            if row.get(field) is not False:
                raise HumanRolePackageError(
                    f"Candidate research must not confer {field.removeprefix('confers_')}."
                )

    for name in (
        "eligible_for_model_training",
        "eligible_for_query_model_training",
        "eligible_for_decision_layer",
        "eligible_for_fpps",
        "eligible_for_warning",
    ):
        if payload.get(name) is not False:
            raise HumanRolePackageError(f"Human-role package safety field {name} must be false.")
    if payload.get("role_evidence_limitation") != ROLE_EVIDENCE_LIMITATION:
        raise HumanRolePackageError("Human-role package lost its evidence limitation.")
    if payload.get("identity_verification_status") != IDENTITY_STATUS:
        raise HumanRolePackageError("Human-role package overstates identity verification.")
    if payload.get("qualification_verification_status") != QUALIFICATION_STATUS:
        raise HumanRolePackageError("Human-role package overstates qualification verification.")

    evidence = _require_sequence(payload.get("evidence"), "evidence")
    evidence_ids: set[str] = set()
    for item in evidence:
        row = _copy_mapping(item, "package evidence row")
        _require_exact_keys(row, _NORMALIZED_EVIDENCE_KEYS, "package evidence row")
        evidence_id = _required_match(row.get("evidence_id"), _EVIDENCE_ID_RE, "evidence_id")
        if evidence_id in evidence_ids:
            raise HumanRolePackageError(f"Duplicate evidence_id in package: {evidence_id}")
        evidence_ids.add(evidence_id)
        _required_choice(row.get("evidence_type"), EVIDENCE_TYPES, "evidence_type")
        _required_text(row.get("role_id"), "role_id")
        _required_match(row.get("person_id"), _PERSON_ID_RE, "person_id")
        _required_sha(row.get("sha256"), f"evidence[{evidence_id}].sha256")
        _captured_text, captured = _strict_utc(
            row.get("captured_at_utc"), "captured_at_utc"
        )
        if captured > package_created:
            raise HumanRolePackageError(f"Evidence {evidence_id} was captured after package creation.")
        _required_text(row.get("attributable_sender"), "attributable_sender")
        _required_text(row.get("attributable_recipient"), "attributable_recipient")
        relative = _safe_relative_path(row.get("package_path"), f"evidence[{evidence_id}].package_path")
        source = _resolve_below(root.resolve(), relative, f"evidence[{evidence_id}]")
        if not source.is_file() or _file_sha256(source) != row["sha256"]:
            raise HumanRolePackageError(f"Evidence file is missing or failed checksum: {evidence_id}")
        if row.get("verification_status") != LOCAL_EVIDENCE_STATUS:
            raise HumanRolePackageError(f"Evidence {evidence_id} overstates verification.")

    appointments = _require_sequence(payload.get("appointments"), "appointments")
    dual_allowed = payload.get("reference_authority_adjudicator_dual_role_allowed")
    if not isinstance(dual_allowed, bool):
        raise HumanRolePackageError(
            "reference_authority_adjudicator_dual_role_allowed must be a JSON boolean."
        )
    _validate_normalized_appointments(
        appointments,
        evidence,
        dual_allowed=dual_allowed,
        package_created=package_created,
        participation_mode=participation,
        annotation_use_scope=use_scope,
    )
    expected_blinding = _is_genuinely_blinded_double_review(appointments)
    if payload.get("genuinely_blinded_double_review") is not expected_blinding:
        raise HumanRolePackageError("Double-review blinding status is inconsistent.")

    receipt_binding = payload.get("calibration_receipt")
    requested = payload.get("formal_review_authorization_requested")
    if not isinstance(requested, bool):
        raise HumanRolePackageError(
            "formal_review_authorization_requested must be a JSON boolean."
        )
    authorized = payload.get("formal_review_authorized")
    if authorized is True:
        if requested is not True:
            raise HumanRolePackageError("Formal review cannot be authorized without an owner request.")
        if not isinstance(receipt_binding, Mapping):
            raise HumanRolePackageError("Formal review authorization requires a calibration receipt.")
    elif authorized is not False:
        raise HumanRolePackageError("formal_review_authorized must be a JSON boolean.")
    if requested and authorized is not True:
        raise HumanRolePackageError(
            "A formal-review request cannot remain represented as authorized without a receipt."
        )
    if not requested and authorized is not False:
        raise HumanRolePackageError("Formal review cannot be authorized when it was not requested.")

    if receipt_binding is not None:
        binding = _copy_mapping(receipt_binding, "calibration_receipt")
        _require_exact_keys(binding, _CALIBRATION_BINDING_KEYS, "calibration_receipt")
        if binding.get("package_path") != "calibration/reviewer_calibration_receipt.json":
            raise HumanRolePackageError("Calibration receipt package path is not canonical.")
        if binding.get("calibration_passed") is not True:
            raise HumanRolePackageError("Bound calibration receipt is not marked passing.")
        declared_file_sha = _required_sha(
            payload.get("calibration_receipt_file_sha256"),
            "calibration_receipt_file_sha256",
        )
        if binding.get("file_sha256") != declared_file_sha:
            raise HumanRolePackageError("Calibration receipt checksum binding is inconsistent.")
        receipt_path = root / "calibration" / "reviewer_calibration_receipt.json"
        if not receipt_path.is_file():
            raise HumanRolePackageError("Bound calibration receipt is missing from the package.")
        if _file_sha256(receipt_path) != binding.get("file_sha256"):
            raise HumanRolePackageError("Bound calibration receipt failed file checksum.")
        try:
            receipt = load_reviewer_calibration_receipt(receipt_path)
        except ReviewerCalibrationError as exc:
            raise HumanRolePackageError(f"Bound calibration receipt is invalid: {exc}") from exc
        _verify_receipt_matches_manifest(payload, binding, receipt)
    else:
        if payload.get("calibration_receipt_file_sha256") is not None:
            raise HumanRolePackageError("A calibration checksum exists without a copied receipt.")
        if payload.get("formal_review_authorized") is not False:
            raise HumanRolePackageError("No calibration receipt means formal review must remain blocked.")
        if payload.get("formal_review_authorized_from_utc") is not None:
            raise HumanRolePackageError("Blocked formal review cannot have an authorization timestamp.")
    expected_status = (
        (
            "formal_review_gate_open_independent_a_b"
            if expected_blinding
            else "formal_review_gate_open_mitigated_non_independent_a"
        )
        if payload.get("formal_review_authorized") is True
        else "formal_review_hold_calibration_or_owner_authorization_pending"
    )
    if payload.get("package_status") != expected_status:
        raise HumanRolePackageError("Human-role package status is inconsistent with the gate.")
    return payload


def _validate_request(payload: Mapping[str, Any], evidence_root: Path) -> dict[str, Any]:
    package_name = _required_match(payload.get("package_name"), _PACKAGE_NAME_RE, "package_name")
    version = payload.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise HumanRolePackageError("version must be a positive integer.")
    created_text, created = _strict_utc(payload.get("created_at_utc"), "created_at_utc")
    participation = _required_choice(payload.get("participation_mode"), PARTICIPATION_MODES, "participation_mode")
    use_scope = _required_choice(payload.get("annotation_use_scope"), ANNOTATION_USE_SCOPES, "annotation_use_scope")
    if payload.get("public_release_requires_separate_project_decision") is not True:
        raise HumanRolePackageError(
            "public_release_requires_separate_project_decision must be true."
        )
    dual_allowed = _required_bool(
        payload.get("reference_authority_adjudicator_dual_role_allowed"),
        "reference_authority_adjudicator_dual_role_allowed",
    )
    requested = _required_bool(
        payload.get("formal_review_authorization_requested"),
        "formal_review_authorization_requested",
    )
    declared_receipt_sha = payload.get("calibration_receipt_file_sha256")
    if declared_receipt_sha is not None:
        declared_receipt_sha = _required_sha(
            declared_receipt_sha, "calibration_receipt_file_sha256"
        )

    candidates: list[dict[str, Any]] = []
    seen_candidates: set[str] = set()
    for index, item in enumerate(_require_sequence(payload.get("candidate_research"), "candidate_research")):
        row = _copy_mapping(item, f"candidate_research[{index}]")
        _require_exact_keys(row, _CANDIDATE_KEYS, f"candidate_research[{index}]")
        candidate_id = _required_match(row.get("candidate_id"), _CANDIDATE_ID_RE, "candidate_id")
        if candidate_id in seen_candidates:
            raise HumanRolePackageError(f"Duplicate candidate_id: {candidate_id}")
        seen_candidates.add(candidate_id)
        researched_text, researched = _strict_utc(row.get("researched_at_utc"), "researched_at_utc")
        if researched > created:
            raise HumanRolePackageError(f"Candidate research {candidate_id} occurs after package creation.")
        categories = tuple(
            sorted(
                {
                    _required_choice(value, frozenset(ROLE_CATEGORIES), "candidate_role_category")
                    for value in _require_sequence(row.get("candidate_role_categories"), "candidate_role_categories")
                }
            )
        )
        if not categories:
            raise HumanRolePackageError(f"Candidate {candidate_id} needs at least one role category.")
        if row.get("research_status") != "public_research_only_not_nominated_or_accepted":
            raise HumanRolePackageError(
                f"Candidate {candidate_id} must remain public research only."
            )
        candidates.append(
            {
                "candidate_id": candidate_id,
                "display_name": _required_text(row.get("display_name"), "display_name"),
                "source_reference": _required_text(row.get("source_reference"), "source_reference"),
                "researched_at_utc": researched_text,
                "candidate_role_categories": list(categories),
                "research_status": "public_research_only_not_nominated_or_accepted",
                "confers_nomination": False,
                "confers_acceptance": False,
                "confers_identity_verification": False,
                "confers_qualification_certification": False,
            }
        )

    evidence_sources, evidence_by_id = _validate_evidence_rows(
        payload.get("evidence"), evidence_root, created
    )
    appointments = _validate_appointments(
        payload.get("appointments"),
        evidence_by_id=evidence_by_id,
        created=created,
        participation_mode=participation,
        annotation_use_scope=use_scope,
        dual_allowed=dual_allowed,
    )
    return {
        "request_schema": REQUEST_SCHEMA,
        "package_name": package_name,
        "version": version,
        "package_id": f"{package_name}_v{version}",
        "event_id": _required_text(payload.get("event_id"), "event_id"),
        "protocol_version": _required_text(payload.get("protocol_version"), "protocol_version"),
        "taxonomy_version": _required_text(payload.get("taxonomy_version"), "taxonomy_version"),
        "created_at_utc": created_text,
        "created_by_person_id": _required_match(payload.get("created_by_person_id"), _PERSON_ID_RE, "created_by_person_id"),
        "participation_mode": participation,
        "annotation_use_scope": use_scope,
        "public_release_requires_separate_project_decision": True,
        "reference_authority_adjudicator_dual_role_allowed": dual_allowed,
        "candidate_research": sorted(candidates, key=lambda row: row["candidate_id"]),
        "appointments": appointments,
        "_evidence_sources": evidence_sources,
        "formal_review_authorization_requested": requested,
        "calibration_receipt_file_sha256": declared_receipt_sha,
        "assumptions": _required_text(payload.get("assumptions"), "assumptions"),
    }


def _validate_evidence_rows(
    value: Any, evidence_root: Path, created: datetime
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(_require_sequence(value, "evidence")):
        row = _copy_mapping(item, f"evidence[{index}]")
        _require_exact_keys(row, _EVIDENCE_KEYS, f"evidence[{index}]")
        evidence_id = _required_match(row.get("evidence_id"), _EVIDENCE_ID_RE, "evidence_id")
        if evidence_id in by_id:
            raise HumanRolePackageError(f"Duplicate evidence_id: {evidence_id}")
        evidence_type = _required_choice(row.get("evidence_type"), EVIDENCE_TYPES, "evidence_type")
        role_id = _required_text(row.get("role_id"), "role_id")
        person_id = _required_match(row.get("person_id"), _PERSON_ID_RE, "person_id")
        relative = _safe_relative_path(row.get("local_path"), f"evidence[{evidence_id}].local_path")
        source = _resolve_below(evidence_root, relative, f"evidence[{evidence_id}]")
        if not source.is_file():
            raise HumanRolePackageError(f"Evidence file does not exist: {evidence_id}")
        declared_sha = _required_sha(row.get("sha256"), f"evidence[{evidence_id}].sha256")
        if _file_sha256(source) != declared_sha:
            raise HumanRolePackageError(f"Evidence SHA-256 mismatch: {evidence_id}")
        captured_text, captured = _strict_utc(row.get("captured_at_utc"), "captured_at_utc")
        if captured > created:
            raise HumanRolePackageError(f"Evidence {evidence_id} was captured after package creation.")
        if row.get("verification_status") != LOCAL_EVIDENCE_STATUS:
            raise HumanRolePackageError(
                f"Evidence {evidence_id} verification_status must be {LOCAL_EVIDENCE_STATUS!r}."
            )
        normalized = {
            "evidence_id": evidence_id,
            "evidence_type": evidence_type,
            "role_id": role_id,
            "person_id": person_id,
            "sha256": declared_sha,
            "captured_at_utc": captured_text,
            "attributable_sender": _required_text(row.get("attributable_sender"), "attributable_sender"),
            "attributable_recipient": _required_text(row.get("attributable_recipient"), "attributable_recipient"),
            "verification_status": LOCAL_EVIDENCE_STATUS,
            "_resolved_source": str(source),
        }
        rows.append(normalized)
        by_id[evidence_id] = normalized
    if not rows:
        raise HumanRolePackageError("Attributable local evidence must not be empty.")
    return sorted(rows, key=lambda row: row["evidence_id"]), by_id


def _validate_appointments(
    value: Any,
    *,
    evidence_by_id: Mapping[str, Mapping[str, Any]],
    created: datetime,
    participation_mode: str,
    annotation_use_scope: str,
    dual_allowed: bool,
) -> list[dict[str, Any]]:
    rows = _require_sequence(value, "appointments")
    if len(rows) != len(ROLE_CATEGORIES):
        raise HumanRolePackageError("Appointments must contain exactly RA, A, B, and C.")
    appointments: list[dict[str, Any]] = []
    category_rows: dict[str, dict[str, Any]] = {}
    seen_role_ids: set[str] = set()
    for index, item in enumerate(rows):
        row = _copy_mapping(item, f"appointments[{index}]")
        _require_exact_keys(row, _APPOINTMENT_KEYS, f"appointments[{index}]")
        category = _required_choice(row.get("role_category"), frozenset(ROLE_CATEGORIES), "role_category")
        if category in category_rows:
            raise HumanRolePackageError(f"Duplicate role category: {category}")
        role_id = _required_match(row.get("role_id"), ROLE_ID_PATTERNS[category], "role_id")
        if role_id in seen_role_ids:
            raise HumanRolePackageError(f"Duplicate role_id: {role_id}")
        seen_role_ids.add(role_id)
        person_id = _required_match(row.get("person_id"), _PERSON_ID_RE, "person_id")
        if row.get("appointment_status") != "accepted_with_attributable_local_evidence":
            raise HumanRolePackageError(
                f"Appointment {role_id} is not an evidenced acceptance."
            )
        accepted_text, accepted = _strict_utc(row.get("accepted_at_utc"), "accepted_at_utc")
        conflict_text, conflict_time = _strict_utc(row.get("conflict_decided_at_utc"), "conflict_decided_at_utc")
        terms_text, terms_time = _strict_utc(row.get("data_terms_accepted_at_utc"), "data_terms_accepted_at_utc")
        retention_text, retention = _strict_utc(row.get("retention_end_utc"), "retention_end_utc")
        if max(accepted, conflict_time, terms_time) > created:
            raise HumanRolePackageError(f"Appointment {role_id} contains a decision after package creation.")
        if retention <= created:
            raise HumanRolePackageError(f"Appointment {role_id} retention_end_utc must be after package creation.")
        conflict_declared = _required_bool(row.get("conflict_declared"), "conflict_declared")
        conflict_decision = _required_choice(row.get("conflict_decision"), CONFLICT_DECISIONS, "conflict_decision")
        if conflict_decision == "no_conflict_declared" and conflict_declared:
            raise HumanRolePackageError(f"Appointment {role_id} declares a conflict but records no conflict.")
        if conflict_decision != "no_conflict_declared" and not conflict_declared:
            raise HumanRolePackageError(f"Appointment {role_id} has controls but conflict_declared=false.")
        controls = _required_text(row.get("conflict_controls"), "conflict_controls")
        if conflict_decision != "no_conflict_declared" and controls.lower() in {"none", "n/a", "na"}:
            raise HumanRolePackageError(f"Appointment {role_id} needs substantive conflict controls.")
        scope = _required_choice(row.get("annotation_use_scope"), ANNOTATION_USE_SCOPES, "annotation_use_scope")
        if scope != annotation_use_scope:
            raise HumanRolePackageError(f"Appointment {role_id} data-use scope differs from package scope.")
        public_permission = _required_bool(row.get("public_release_permission"), "public_release_permission")
        if scope == "internal_research_only" and public_permission:
            raise HumanRolePackageError(
                f"Appointment {role_id} cannot grant public release under internal-only terms."
            )
        compensation = _required_choice(row.get("compensation_basis"), PARTICIPATION_MODES, "compensation_basis")
        if compensation != participation_mode:
            raise HumanRolePackageError(f"Appointment {role_id} compensation differs from package terms.")
        project_operator = _required_bool(row.get("project_operator"), "project_operator")
        prior_exposure = _required_bool(
            row.get("prior_prohibited_evidence_exposure"),
            "prior_prohibited_evidence_exposure",
        )
        lane = _required_choice(row.get("review_lane"), REVIEW_LANES, "review_lane")
        independence_controls = _required_text(row.get("independence_controls"), "independence_controls")

        evidence_refs = {
            "acceptance_evidence_id": "role_acceptance",
            "conflict_evidence_id": "conflict_disclosure_and_decision",
            "data_terms_evidence_id": "participant_data_use_terms",
            "qualification_evidence_id": "qualification_basis",
        }
        normalized_refs: dict[str, str] = {}
        for field, expected_type in evidence_refs.items():
            evidence_id = _required_match(row.get(field), _EVIDENCE_ID_RE, field)
            _require_evidence_binding(
                evidence_by_id, evidence_id, expected_type, role_id, person_id
            )
            normalized_refs[field] = evidence_id
        for field, decision_time in (
            ("acceptance_evidence_id", accepted),
            ("conflict_evidence_id", conflict_time),
            ("data_terms_evidence_id", terms_time),
        ):
            evidence_time = _strict_utc(
                evidence_by_id[normalized_refs[field]]["captured_at_utc"],
                f"evidence[{normalized_refs[field]}].captured_at_utc",
            )[1]
            if evidence_time < decision_time:
                raise HumanRolePackageError(
                    f"Evidence {normalized_refs[field]} was captured before its declared decision."
                )

        approval_role = row.get("independence_approved_by_role_id")
        approval_evidence_id = row.get("independence_decision_evidence_id")
        if category == "reviewer_b":
            if project_operator or prior_exposure or lane != "independent_blinded":
                raise HumanRolePackageError(
                    "Reviewer B must be a genuinely independent, blinded, non-operator lane."
                )
            if approval_role is not None or approval_evidence_id is not None:
                raise HumanRolePackageError("Independent Reviewer B cannot use mitigation approval.")
        elif category == "reviewer_a":
            has_operator_conflict = project_operator or prior_exposure
            if has_operator_conflict:
                if not conflict_declared or conflict_decision == "no_conflict_declared":
                    raise HumanRolePackageError(
                        "Operator/exposed Reviewer A must declare and manage the conflict."
                    )
                if lane != "authority_approved_mitigated_non_independent":
                    raise HumanRolePackageError(
                        "Operator/exposed Reviewer A cannot be represented as independently blinded."
                    )
                if independence_controls.lower() in {"none", "n/a", "na"}:
                    raise HumanRolePackageError(
                        "Mitigated non-independent Reviewer A needs substantive controls."
                    )
                approval_role = _required_match(
                    approval_role, ROLE_ID_PATTERNS["reference_authority"],
                    "independence_approved_by_role_id",
                )
                approval_evidence_id = _required_match(
                    approval_evidence_id, _EVIDENCE_ID_RE,
                    "independence_decision_evidence_id",
                )
            else:
                if lane != "independent_blinded":
                    raise HumanRolePackageError(
                        "Unexposed Reviewer A must use the independent blinded lane."
                    )
                if approval_role is not None or approval_evidence_id is not None:
                    raise HumanRolePackageError("Independent Reviewer A cannot use mitigation approval.")
        else:
            if project_operator or prior_exposure or lane != "authority_role_not_blinded":
                raise HumanRolePackageError(
                    f"Authority appointment {role_id} must use authority_role_not_blinded."
                )
            if approval_role is not None or approval_evidence_id is not None:
                raise HumanRolePackageError(f"Authority appointment {role_id} cannot use mitigation approval.")

        normalized = {
            "role_id": role_id,
            "role_category": category,
            "person_id": person_id,
            "appointment_status": "accepted_with_attributable_local_evidence",
            "accepted_at_utc": accepted_text,
            **normalized_refs,
            "conflict_declared": conflict_declared,
            "conflict_decision": conflict_decision,
            "conflict_controls": controls,
            "conflict_decided_by_person_id": _required_match(row.get("conflict_decided_by_person_id"), _PERSON_ID_RE, "conflict_decided_by_person_id"),
            "conflict_decided_at_utc": conflict_text,
            "data_terms_accepted_at_utc": terms_text,
            "annotation_use_scope": scope,
            "public_release_permission": public_permission,
            "retention_end_utc": retention_text,
            "withdrawal_terms": _required_text(row.get("withdrawal_terms"), "withdrawal_terms"),
            "compensation_basis": compensation,
            "qualification_summary": _required_text(row.get("qualification_summary"), "qualification_summary"),
            "identity_status": IDENTITY_STATUS,
            "qualification_status": QUALIFICATION_STATUS,
            "project_operator": project_operator,
            "prior_prohibited_evidence_exposure": prior_exposure,
            "review_lane": lane,
            "independence_controls": independence_controls,
            "independence_approved_by_role_id": approval_role,
            "independence_decision_evidence_id": approval_evidence_id,
        }
        appointments.append(normalized)
        category_rows[category] = normalized

    if set(category_rows) != set(ROLE_CATEGORIES):
        raise HumanRolePackageError("Appointments do not exactly cover RA, A, B, and C.")
    a = category_rows["reviewer_a"]
    b = category_rows["reviewer_b"]
    ra = category_rows["reference_authority"]
    c = category_rows["adjudicator_c"]
    if a["person_id"] == b["person_id"]:
        raise HumanRolePackageError("Reviewer A and Reviewer B must be different humans.")
    if ra["person_id"] in {a["person_id"], b["person_id"]}:
        raise HumanRolePackageError("Reference Authority must be distinct from A and B.")
    if c["person_id"] in {a["person_id"], b["person_id"]}:
        raise HumanRolePackageError("Adjudicator C must be distinct from A and B.")
    if ra["person_id"] == c["person_id"] and not dual_allowed:
        raise HumanRolePackageError("RA=C requires explicit dual-role allowance.")
    person_roles: dict[str, list[str]] = {}
    for appointment in appointments:
        person_roles.setdefault(appointment["person_id"], []).append(appointment["role_category"])
    for person_id, categories in person_roles.items():
        if len(categories) > 1 and set(categories) != {"reference_authority", "adjudicator_c"}:
            raise HumanRolePackageError(f"Person {person_id} has an impermissible multi-role assignment.")

    if a["review_lane"] == "authority_approved_mitigated_non_independent":
        if a["independence_approved_by_role_id"] != ra["role_id"]:
            raise HumanRolePackageError(
                "Mitigated Reviewer A must be approved by the appointed Reference Authority."
            )
        _require_evidence_binding(
            evidence_by_id,
            a["independence_decision_evidence_id"],
            "independence_mitigation_approval",
            ra["role_id"],
            ra["person_id"],
        )
        approval_time = _strict_utc(
            evidence_by_id[a["independence_decision_evidence_id"]]["captured_at_utc"],
            "independence mitigation captured_at_utc",
        )[1]
        if approval_time < _strict_utc(a["conflict_decided_at_utc"], "conflict_decided_at_utc")[1]:
            raise HumanRolePackageError(
                "Reviewer A mitigation approval evidence predates the conflict decision."
            )
    return sorted(appointments, key=lambda row: ROLE_CATEGORIES.index(row["role_category"]))


def _validate_calibration_binding(
    normalized: Mapping[str, Any], receipt_path: Path | None
) -> dict[str, Any] | None:
    declared_sha = normalized.get("calibration_receipt_file_sha256")
    requested = normalized["formal_review_authorization_requested"]
    if receipt_path is None:
        if declared_sha is not None:
            raise HumanRolePackageError("A calibration checksum was declared but no receipt path was supplied.")
        if requested:
            raise HumanRolePackageError(
                "Formal review remains blocked without an exact passing calibration receipt."
            )
        return None
    if not receipt_path.is_file():
        raise HumanRolePackageError(f"Calibration receipt does not exist: {receipt_path}")
    file_sha = _file_sha256(receipt_path)
    if declared_sha is None or file_sha != declared_sha:
        raise HumanRolePackageError("Calibration receipt file SHA-256 is absent or mismatched.")
    try:
        receipt = load_reviewer_calibration_receipt(receipt_path)
    except ReviewerCalibrationError as exc:
        raise HumanRolePackageError(f"Calibration receipt is not an exact passing receipt: {exc}") from exc
    role_by_category = {row["role_category"]: row for row in normalized["appointments"]}
    expected_reviewers = {
        role_by_category["reviewer_a"]["role_id"],
        role_by_category["reviewer_b"]["role_id"],
    }
    if set(receipt.reviewer_ids) != expected_reviewers:
        raise HumanRolePackageError(
            "Calibration receipt reviewer ids do not exactly match appointed A and B."
        )
    if receipt.protocol_version != normalized["protocol_version"]:
        raise HumanRolePackageError("Calibration receipt protocol does not match the role package.")
    if receipt.taxonomy_version != normalized["taxonomy_version"]:
        raise HumanRolePackageError("Calibration receipt taxonomy does not match the role package.")
    created = _strict_utc(normalized["created_at_utc"], "created_at_utc")[1]
    if requested and created < receipt.formal_review_not_before_utc:
        raise HumanRolePackageError(
            "The role package cannot authorize formal review before the receipt not-before time."
        )
    completion = receipt.calibration_completed_at_utc
    for appointment in normalized["appointments"]:
        for field in (
            "accepted_at_utc",
            "conflict_decided_at_utc",
            "data_terms_accepted_at_utc",
        ):
            if _strict_utc(appointment[field], field)[1] > completion:
                raise HumanRolePackageError(
                    f"Appointment {appointment['role_id']} was not fully accepted before calibration completion."
                )
    if requested:
        for evidence in normalized["_evidence_sources"]:
            if _strict_utc(evidence["captured_at_utc"], "captured_at_utc")[1] > completion:
                raise HumanRolePackageError(
                    f"Evidence {evidence['evidence_id']} was not captured before calibration completion."
                )
    return {
        "package_path": "calibration/reviewer_calibration_receipt.json",
        "file_sha256": file_sha,
        "receipt_sha256": receipt.receipt_sha256,
        "reviewer_ids": list(receipt.reviewer_ids),
        "protocol_version": receipt.protocol_version,
        "taxonomy_version": receipt.taxonomy_version,
        "calibration_completed_at_utc": _iso_utc(receipt.calibration_completed_at_utc),
        "formal_review_not_before_utc": _iso_utc(receipt.formal_review_not_before_utc),
        "calibration_passed": True,
    }


def _validate_version_lineage(
    normalized: Mapping[str, Any], parent: Mapping[str, Any] | None
) -> None:
    version = normalized["version"]
    if parent is None:
        if version != 1:
            raise HumanRolePackageError("An initial human-role package must use version=1.")
        return
    if version != int(parent["version"]) + 1:
        raise HumanRolePackageError("Human-role package versions must increment by exactly one.")
    for field in ("package_name", "event_id", "protocol_version", "taxonomy_version"):
        if normalized[field] != parent[field]:
            raise HumanRolePackageError(f"Versioned role package cannot change {field}.")
    if _strict_utc(normalized["created_at_utc"], "created_at_utc")[1] <= _strict_utc(parent["created_at_utc"], "parent.created_at_utc")[1]:
        raise HumanRolePackageError("Child package creation time must be after its parent.")
    parent_roles = {row["role_id"]: row["person_id"] for row in parent["appointments"]}
    for row in normalized["appointments"]:
        if row["role_id"] in parent_roles and parent_roles[row["role_id"]] != row["person_id"]:
            raise HumanRolePackageError(
                f"Stable role id {row['role_id']} cannot be reassigned to another person."
            )


def _validate_normalized_appointments(
    appointments: Sequence[Any],
    evidence: Sequence[Any],
    *,
    dual_allowed: bool,
    package_created: datetime,
    participation_mode: str,
    annotation_use_scope: str,
) -> None:
    evidence_by_id = {
        row["evidence_id"]: row
        for row in (_copy_mapping(item, "evidence") for item in evidence)
    }
    request_rows: list[dict[str, Any]] = []
    for item in appointments:
        row = _copy_mapping(item, "appointment")
        _require_exact_keys(row, _NORMALIZED_APPOINTMENT_KEYS, "appointment")
        if row.get("identity_status") != IDENTITY_STATUS or row.get("qualification_status") != QUALIFICATION_STATUS:
            raise HumanRolePackageError("Appointment overstates identity or qualification verification.")
        request_rows.append({key: row[key] for key in _APPOINTMENT_KEYS})
    recomputed = _validate_appointments(
        request_rows,
        evidence_by_id=evidence_by_id,
        created=package_created,
        participation_mode=participation_mode,
        annotation_use_scope=annotation_use_scope,
        dual_allowed=dual_allowed,
    )
    if list(appointments) != recomputed:
        raise HumanRolePackageError(
            "Frozen appointments are not in canonical normalized order or content."
        )


def _verify_receipt_matches_manifest(payload: Mapping[str, Any], binding: Mapping[str, Any], receipt: Any) -> None:
    roles = {row["role_category"]: row for row in payload["appointments"]}
    expected = {roles["reviewer_a"]["role_id"], roles["reviewer_b"]["role_id"]}
    if set(receipt.reviewer_ids) != expected or set(binding.get("reviewer_ids", ())) != expected:
        raise HumanRolePackageError("Bound receipt does not exactly match appointed A and B.")
    if binding.get("receipt_sha256") != receipt.receipt_sha256:
        raise HumanRolePackageError("Bound calibration receipt self-hash is inconsistent.")
    expected_binding = {
        "protocol_version": receipt.protocol_version,
        "taxonomy_version": receipt.taxonomy_version,
        "calibration_completed_at_utc": _iso_utc(receipt.calibration_completed_at_utc),
        "formal_review_not_before_utc": _iso_utc(receipt.formal_review_not_before_utc),
    }
    for field, expected in expected_binding.items():
        if binding.get(field) != expected:
            raise HumanRolePackageError(f"Bound calibration {field} is inconsistent.")
    if receipt.protocol_version != payload.get("protocol_version") or receipt.taxonomy_version != payload.get("taxonomy_version"):
        raise HumanRolePackageError("Bound calibration semantics differ from the role package.")
    if payload.get("formal_review_authorized") is True:
        authorized_from = payload.get("formal_review_authorized_from_utc")
        if authorized_from != _iso_utc(receipt.formal_review_not_before_utc):
            raise HumanRolePackageError("Formal-review authorization time differs from receipt.")
        created = _strict_utc(payload.get("created_at_utc"), "created_at_utc")[1]
        if created < receipt.formal_review_not_before_utc:
            raise HumanRolePackageError("Formal review was authorized before its not-before time.")
        for appointment in payload["appointments"]:
            for field in (
                "accepted_at_utc",
                "conflict_decided_at_utc",
                "data_terms_accepted_at_utc",
            ):
                if _strict_utc(appointment[field], field)[1] > receipt.calibration_completed_at_utc:
                    raise HumanRolePackageError(
                        f"Appointment {appointment['role_id']} was incomplete at calibration."
                    )
        for evidence in payload["evidence"]:
            if _strict_utc(evidence["captured_at_utc"], "captured_at_utc")[1] > receipt.calibration_completed_at_utc:
                raise HumanRolePackageError(
                    f"Evidence {evidence['evidence_id']} was captured after calibration completion."
                )
    elif payload.get("formal_review_authorized_from_utc") is not None:
        raise HumanRolePackageError("A formal-review hold cannot have an authorization timestamp.")


def _require_evidence_binding(
    evidence_by_id: Mapping[str, Mapping[str, Any]],
    evidence_id: Any,
    expected_type: str,
    role_id: Any,
    person_id: Any,
) -> None:
    if not isinstance(evidence_id, str) or evidence_id not in evidence_by_id:
        raise HumanRolePackageError(f"Missing referenced evidence: {evidence_id!r}")
    evidence = evidence_by_id[evidence_id]
    if evidence.get("evidence_type") != expected_type:
        raise HumanRolePackageError(f"Evidence {evidence_id} has the wrong evidence_type.")
    if evidence.get("role_id") != role_id or evidence.get("person_id") != person_id:
        raise HumanRolePackageError(f"Evidence {evidence_id} is attributed to another role or person.")


def _is_genuinely_blinded_double_review(appointments: Sequence[Mapping[str, Any]]) -> bool:
    reviewers = [row for row in appointments if row.get("role_category") in {"reviewer_a", "reviewer_b"}]
    return len(reviewers) == 2 and all(
        row.get("review_lane") == "independent_blinded"
        and row.get("project_operator") is False
        and row.get("prior_prohibited_evidence_exposure") is False
        for row in reviewers
    )


def _copy_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise HumanRolePackageError(f"{field} must be a JSON object.")
    return dict(value)


def _require_sequence(value: Any, field: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise HumanRolePackageError(f"{field} must be a JSON array.")
    return list(value)


def _require_exact_keys(value: Mapping[str, Any], expected: frozenset[str], field: str) -> None:
    actual = set(value)
    if actual != set(expected):
        raise HumanRolePackageError(
            f"{field} keys differ; missing={sorted(set(expected) - actual)}, extra={sorted(actual - set(expected))}."
        )


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HumanRolePackageError(f"{field} must be a non-blank string.")
    return value.strip()


def _required_match(value: Any, pattern: re.Pattern[str], field: str) -> str:
    text = _required_text(value, field)
    if pattern.fullmatch(text) is None:
        raise HumanRolePackageError(f"{field} has an invalid stable identifier: {text!r}.")
    return text


def _required_choice(value: Any, choices: frozenset[str], field: str) -> str:
    text = _required_text(value, field)
    if text not in choices:
        raise HumanRolePackageError(f"{field} must be one of {sorted(choices)}.")
    return text


def _required_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise HumanRolePackageError(f"{field} must be a JSON boolean.")
    return value


def _required_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA_RE.fullmatch(value) is None:
        raise HumanRolePackageError(f"{field} must be a lowercase SHA-256 digest.")
    return value


def _strict_utc(value: Any, field: str) -> tuple[str, datetime]:
    if not isinstance(value, str) or _UTC_RE.fullmatch(value) is None:
        raise HumanRolePackageError(f"{field} must use exact YYYY-MM-DDTHH:MM:SSZ UTC format.")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise HumanRolePackageError(f"{field} is not a real UTC timestamp.") from exc
    return value, parsed


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_relative_path(value: Any, field: str) -> Path:
    text = _required_text(value, field).replace("\\", "/")
    pure = PurePosixPath(text)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts) or ":" in text:
        raise HumanRolePackageError(f"{field} must be a safe relative local path.")
    return Path(*pure.parts)


def _resolve_below(root: Path, relative: Path, field: str) -> Path:
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise HumanRolePackageError(f"{field} escapes its allowed root.") from exc
    return resolved


def _load_json_object(path: Path, description: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HumanRolePackageError(f"Could not load {description} {path}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise HumanRolePackageError(f"{description} root must be a JSON object.")
    return dict(payload)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise HumanRolePackageError(f"Could not hash local file {path}: {exc}") from exc
    return digest.hexdigest()


def _canonical_json_sha256(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
