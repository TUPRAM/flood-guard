"""Freeze a fail-closed Reference Authority design-decision package.

The package records a human Reference Authority's attributable local decision
about three pre-calibration inputs: one provisional parent-tile reserve
candidate, an optional governed VV/VH review-derivative receipt, and one fixed
reference-procedure document version.  It deliberately stops before reserve
construction, reference geometry, query selection, calibration, or review.

Software can verify local bytes, hashes, timestamps, declared attribution, and
cross-artifact consistency.  It cannot independently authenticate the sender,
certify expertise, or prove that an opaque email/PDF/message says what the
structured decision request records.  The immutable package preserves that
limitation rather than promoting local evidence into a stronger claim.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import csv
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from typing import Any

from floodguard.label_factory.calibration_reserve import (
    CalibrationReserveError,
    verify_calibration_reserve_design_package,
)
from floodguard.label_factory.human_roles import (
    HumanRolePackageError,
    validate_human_role_package,
)
from floodguard.label_factory.review_derivatives import (
    ReviewDerivativeLineageError,
    load_review_derivative_lineage_receipt,
)


REQUEST_SCHEMA = "floodguard.reference_authority_design_decision_request.v1"
PACKAGE_SCHEMA = "floodguard.reference_authority_design_approval.v1"
BUILDER_ID = "floodguard.label_factory.reference_authority_approval@v1"
MANIFEST_NAME = "reference_authority_approval.json"

APPROVED_STATUS = "approved_next_construction_only"
REJECTED_STATUS = "rejected_no_construction_authority"
EVIDENCE_VERIFICATION_STATUS = "local_copy_hash_and_declared_attribution_only"
SEMANTIC_VERIFICATION_STATUS = "not_verified_from_opaque_evidence_by_software"

_UTC_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_SHA_RE = re.compile(r"[0-9a-f]{64}")
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{2,127}")
_VERSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_ROLE_ID_RE = re.compile(r"FG-RA-[0-9]{3,}")
_PERSON_ID_RE = re.compile(r"FG-HUM-[0-9]{3,}")
_EVIDENCE_ID_RE = re.compile(r"FG-RA-DEC-[0-9]{3,}")
_CANDIDATE_ID_RE = re.compile(r"CALRES-[0-9A-F]{12}")

_TOP_LEVEL_REQUEST_KEYS = frozenset(
    {
        "schema",
        "package_id",
        "event_id",
        "created_at_utc",
        "reference_authority_role_id",
        "reference_authority_person_id",
        "decision_evidence",
        "reserve_design_decision",
        "review_derivative_decision",
        "reference_procedure_decision",
        "authority_attestations",
        "assumptions",
    }
)
_DECISION_EVIDENCE_KEYS = frozenset(
    {
        "evidence_id",
        "evidence_type",
        "local_path",
        "sha256",
        "decision_at_utc",
        "captured_at_utc",
        "attributable_sender",
        "attributable_recipient",
        "attributable_sender_person_id",
    }
)
_RESERVE_DECISION_KEYS = frozenset(
    {"design_id", "chosen_candidate_id", "decision", "rationale"}
)
_DERIVATIVE_DECISION_KEYS = frozenset(
    {"decision", "receipt_sha256", "rationale"}
)
_PROCEDURE_DECISION_KEYS = frozenset(
    {"document_version", "document_sha256", "decision", "rationale"}
)
_ATTESTATION_KEYS = frozenset(
    {
        "reserve_uses_static_non_label_context_only",
        "reserve_candidate_is_not_flood_truth",
        "calibration_and_retest_queries_remain_unselected_and_unseen",
        "reference_procedure_is_fixed_to_the_bound_hash_and_version",
        "derivative_decision_governs_display_inclusion_only",
        "no_bundle_calibration_or_formal_review_is_authorized",
        "human_role_evidence_limitation_is_acknowledged",
    }
)
_EVIDENCE_TYPES = frozenset({"email_export", "signed_pdf", "message_export"})
_BINARY_DECISIONS = frozenset({"approved", "rejected"})
_DERIVATIVE_DECISIONS = frozenset({"approved", "rejected", "not_submitted"})

_PACKAGE_KEYS = frozenset(
    {
        "artifact_schema",
        "builder",
        "package_id",
        "event_id",
        "created_at_utc",
        "approval_status",
        "reference_authority",
        "decision_evidence",
        "reserve_design_binding",
        "review_derivative_decision",
        "reference_procedure_binding",
        "authority_attestations",
        "authorization_scope",
        "safety",
        "artifacts",
        "assumptions",
        "evidence_limitation",
        "manifest_sha256",
    }
)

_SAFETY_FALSE_FIELDS = (
    "creates_or_changes_dataset_roles",
    "creates_reference_geometry_or_labels",
    "selects_calibration_query_ids",
    "selects_retest_query_ids",
    "creates_review_bundles",
    "review_bundle_authorized",
    "calibration_execution_authorized",
    "formal_review_authorized",
    "eligible_for_human_annotation",
    "eligible_for_review_queue",
    "eligible_for_model_training",
    "eligible_for_query_model_training",
    "eligible_for_training_after_human_review",
    "eligible_for_decision_layer",
    "eligible_for_fpps",
    "eligible_for_warning",
)

_EVIDENCE_LIMITATION = (
    "This package verifies local file presence, exact bytes, declared attribution, "
    "UTC ordering, and artifact bindings only. It does not independently "
    "authenticate the sender, validate a digital signature, certify expertise, "
    "or verify that opaque evidence semantically matches the structured decision."
)


class ReferenceAuthorityApprovalError(ValueError):
    """Raised when an authority decision cannot be frozen safely."""


def load_reference_authority_approval_request(
    path: str | Path,
) -> dict[str, Any]:
    """Load a strict decision request; relational checks occur during build."""

    payload = _load_json_object(Path(path), "Reference Authority request")
    _require_exact_keys(payload, _TOP_LEVEL_REQUEST_KEYS, "decision request")
    if payload.get("schema") != REQUEST_SCHEMA:
        raise ReferenceAuthorityApprovalError(
            f"Request schema must be exactly {REQUEST_SCHEMA!r}."
        )
    return payload


def build_reference_authority_approval_package(
    request: Mapping[str, Any] | str | Path,
    *,
    evidence_root: str | Path,
    human_role_package: str | Path,
    calibration_reserve_design_package: str | Path,
    reference_procedure_path: str | Path,
    output_directory: str | Path,
    review_derivative_lineage_receipt_path: str | Path | None = None,
) -> Path:
    """Validate exact inputs and freeze one immutable decision package.

    An approved result authorizes only a *separate* canonical reserve/reference
    construction step.  This function never mutates the source packages and
    never creates query IDs, role assignments, labels, review bundles, or a
    formal-review authorization.
    """

    raw_request = (
        load_reference_authority_approval_request(request)
        if isinstance(request, (str, Path))
        else dict(request)
    )
    normalized = _normalize_request(raw_request)
    evidence_root_path = _required_directory(evidence_root, "evidence root")
    human_root = _required_directory(human_role_package, "human-role package")
    design_root = _required_directory(
        calibration_reserve_design_package,
        "calibration reserve design package",
    )
    procedure_source = _required_file(
        reference_procedure_path, "reference procedure"
    )
    derivative_source = (
        _required_file(
            review_derivative_lineage_receipt_path,
            "review-derivative lineage receipt",
        )
        if review_derivative_lineage_receipt_path is not None
        else None
    )

    human_manifest, authority = _validate_human_role_binding(
        human_root, normalized
    )
    design_receipt, chosen_candidate = _validate_reserve_binding(
        design_root, normalized
    )
    derivative = _validate_derivative_binding(derivative_source, normalized)
    _validate_reference_procedure(procedure_source, normalized)
    evidence_source = _validate_decision_evidence(
        evidence_root_path,
        normalized,
        human_manifest=human_manifest,
        authority=authority,
        design_receipt=design_receipt,
        derivative=derivative,
    )

    target = Path(output_directory)
    if target.exists():
        raise ReferenceAuthorityApprovalError(
            f"Approval package is immutable and already exists: {target}"
        )
    parent_existed = target.parent.exists()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
    )
    try:
        human_copy = temporary / "bindings" / "human_role_package"
        _copy_human_role_package(human_root, human_manifest, human_copy)

        design_copy = temporary / "bindings" / "calibration_reserve_design"
        _copy_calibration_design_package(design_root, design_receipt, design_copy)

        derivative_copy: Path | None = None
        if derivative_source is not None:
            derivative_copy = (
                temporary
                / "bindings"
                / "review_derivative_lineage_receipt.json"
            )
            _copy_file(derivative_source, derivative_copy)

        evidence_suffix = evidence_source.suffix.lower()
        evidence_copy = (
            temporary
            / "evidence"
            / f"reference_authority_decision{evidence_suffix}"
        )
        _copy_file(evidence_source, evidence_copy)

        procedure_suffix = procedure_source.suffix.lower() or ".bin"
        procedure_copy = (
            temporary
            / "reference"
            / f"reference_procedure{procedure_suffix}"
        )
        _copy_file(procedure_source, procedure_copy)

        construction_authorized = (
            normalized["reserve_design_decision"]["decision"] == "approved"
            and normalized["reference_procedure_decision"]["decision"]
            == "approved"
        )
        approval_status = (
            APPROVED_STATUS if construction_authorized else REJECTED_STATUS
        )
        payload: dict[str, Any] = {
            "artifact_schema": PACKAGE_SCHEMA,
            "builder": BUILDER_ID,
            "package_id": normalized["package_id"],
            "event_id": normalized["event_id"],
            "created_at_utc": normalized["created_at_utc"],
            "approval_status": approval_status,
            "reference_authority": {
                "role_id": authority["role_id"],
                "person_id": authority["person_id"],
                "appointment_status": authority["appointment_status"],
                "accepted_at_utc": authority["accepted_at_utc"],
                "human_role_package_id": human_manifest["package_id"],
                "human_role_manifest_sha256": human_manifest["manifest_sha256"],
                "human_role_manifest_file_sha256": _file_sha256(
                    human_root / "human_role_package.json"
                ),
                "identity_status": authority["identity_status"],
                "qualification_status": authority["qualification_status"],
                "role_evidence_limitation": human_manifest[
                    "role_evidence_limitation"
                ],
                "package_path": "bindings/human_role_package",
            },
            "decision_evidence": {
                "evidence_id": normalized["decision_evidence"]["evidence_id"],
                "evidence_type": normalized["decision_evidence"]["evidence_type"],
                "package_path": evidence_copy.relative_to(temporary).as_posix(),
                "file_sha256": _file_sha256(evidence_copy),
                "decision_at_utc": normalized["decision_evidence"][
                    "decision_at_utc"
                ],
                "captured_at_utc": normalized["decision_evidence"][
                    "captured_at_utc"
                ],
                "attributable_sender": normalized["decision_evidence"][
                    "attributable_sender"
                ],
                "attributable_recipient": normalized["decision_evidence"][
                    "attributable_recipient"
                ],
                "attributable_sender_person_id": authority["person_id"],
                "verification_status": EVIDENCE_VERIFICATION_STATUS,
                "semantic_verification_status": SEMANTIC_VERIFICATION_STATUS,
            },
            "reserve_design_binding": {
                "decision": normalized["reserve_design_decision"]["decision"],
                "rationale": normalized["reserve_design_decision"]["rationale"],
                "design_id": design_receipt["design_id"],
                "design_receipt_sha256": design_receipt["receipt_sha256"],
                "design_receipt_file_sha256": _file_sha256(
                    design_root / "design_receipt.json"
                ),
                "candidate_combinations_sha256": design_receipt["outputs"]
                ["candidate_combinations"]["sha256"],
                "chosen_candidate_id": chosen_candidate["candidate_id"],
                "source_design_status": design_receipt["status"],
                "package_path": "bindings/calibration_reserve_design",
                "changes_dataset_roles": False,
                "selects_query_ids": False,
            },
            "review_derivative_decision": _derivative_receipt_binding(
                normalized,
                derivative,
                derivative_copy,
                root=temporary,
            ),
            "reference_procedure_binding": {
                "decision": normalized["reference_procedure_decision"][
                    "decision"
                ],
                "rationale": normalized["reference_procedure_decision"][
                    "rationale"
                ],
                "document_version": normalized["reference_procedure_decision"]
                ["document_version"],
                "package_path": procedure_copy.relative_to(temporary).as_posix(),
                "file_sha256": _file_sha256(procedure_copy),
            },
            "authority_attestations": normalized["authority_attestations"],
            "authorization_scope": {
                "may_start_separate_canonical_reserve_construction": (
                    construction_authorized
                ),
                "may_start_separate_reference_construction": (
                    construction_authorized
                ),
                "may_include_bound_review_derivatives_in_that_next_construction": (
                    construction_authorized
                    and normalized["review_derivative_decision"]["decision"]
                    == "approved"
                ),
                "calibration_query_selection": False,
                "calibration_execution": False,
                "review_bundle_construction": False,
                "formal_review": False,
            },
            "safety": {
                **{field: False for field in _SAFETY_FALSE_FIELDS},
                "calibration_query_ids": [],
                "retest_query_ids": [],
            },
            "artifacts": [],
            "assumptions": normalized["assumptions"],
            "evidence_limitation": _EVIDENCE_LIMITATION,
        }
        readme = temporary / "README.md"
        readme.write_text(
            _readme_text(payload), encoding="utf-8", newline="\n"
        )
        payload["artifacts"] = _artifact_records(temporary)
        manifest = {
            **payload,
            "manifest_sha256": _canonical_json_sha256(payload),
        }
        manifest_path = temporary / MANIFEST_NAME
        manifest_path.write_text(
            json.dumps(
                manifest,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        validate_reference_authority_approval_package(temporary)
        try:
            temporary.rename(target)
        except FileExistsError as exc:
            raise ReferenceAuthorityApprovalError(
                f"Approval package is immutable and already exists: {target}"
            ) from exc
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        if not parent_existed:
            try:
                target.parent.rmdir()
            except OSError:
                pass
        raise
    return target


def validate_reference_authority_approval_package(
    package_directory: str | Path,
) -> dict[str, Any]:
    """Revalidate a complete immutable decision package from its copied bytes."""

    root = _required_directory(package_directory, "authority approval package")
    manifest = _load_json_object(root / MANIFEST_NAME, "authority approval manifest")
    _require_exact_keys(manifest, _PACKAGE_KEYS, "authority approval manifest")
    if manifest.get("artifact_schema") != PACKAGE_SCHEMA:
        raise ReferenceAuthorityApprovalError(
            f"Package schema must be exactly {PACKAGE_SCHEMA!r}."
        )
    if manifest.get("builder") != BUILDER_ID:
        raise ReferenceAuthorityApprovalError("Unknown authority-package builder.")
    declared = _required_sha(manifest.get("manifest_sha256"), "manifest_sha256")
    unsigned = dict(manifest)
    unsigned.pop("manifest_sha256", None)
    if _canonical_json_sha256(unsigned) != declared:
        raise ReferenceAuthorityApprovalError(
            "Authority approval manifest self-hash mismatch."
        )

    package_id = _required_match(manifest.get("package_id"), _ID_RE, "package_id")
    event_id = _required_text(manifest.get("event_id"), "event_id")
    _created_text, created = _strict_utc(
        manifest.get("created_at_utc"), "created_at_utc"
    )
    _validate_artifacts(root, manifest.get("artifacts"))
    if Path(MANIFEST_NAME) in {
        Path(row["package_path"]) for row in manifest["artifacts"]
    }:
        raise ReferenceAuthorityApprovalError(
            "Artifact inventory must not recursively include its own manifest."
        )

    authority_record = _require_mapping(
        manifest.get("reference_authority"), "reference_authority"
    )
    human_relative = _safe_relative_path(
        authority_record.get("package_path"), "reference_authority.package_path"
    )
    human_root = _resolve_below(root, human_relative, "human-role package")
    try:
        human_manifest = validate_human_role_package(human_root)
    except (HumanRolePackageError, OSError) as exc:
        raise ReferenceAuthorityApprovalError(
            f"Copied human-role package is invalid: {exc}"
        ) from exc
    authority = _one_reference_authority(human_manifest)
    if human_manifest.get("formal_review_authorized") is not False:
        raise ReferenceAuthorityApprovalError(
            "Authority decision requires a pre-calibration human-role package."
        )
    if human_manifest.get("formal_review_authorization_requested") is not False:
        raise ReferenceAuthorityApprovalError(
            "Pre-calibration human-role package cannot request formal review."
        )
    if human_manifest.get("calibration_receipt") is not None:
        raise ReferenceAuthorityApprovalError(
            "Pre-calibration human-role package must not bind a calibration receipt."
        )
    expected_authority = {
        "role_id": authority["role_id"],
        "person_id": authority["person_id"],
        "appointment_status": authority["appointment_status"],
        "accepted_at_utc": authority["accepted_at_utc"],
        "human_role_package_id": human_manifest["package_id"],
        "human_role_manifest_sha256": human_manifest["manifest_sha256"],
        "human_role_manifest_file_sha256": _file_sha256(
            human_root / "human_role_package.json"
        ),
        "identity_status": authority["identity_status"],
        "qualification_status": authority["qualification_status"],
        "role_evidence_limitation": human_manifest["role_evidence_limitation"],
        "package_path": human_relative.as_posix(),
    }
    if authority_record != expected_authority:
        raise ReferenceAuthorityApprovalError(
            "Reference Authority binding differs from the copied role package."
        )
    if human_manifest.get("event_id") != event_id:
        raise ReferenceAuthorityApprovalError(
            "Human-role package event differs from the authority package."
        )

    evidence = _require_mapping(
        manifest.get("decision_evidence"), "decision_evidence"
    )
    evidence_path = _resolve_below(
        root,
        _safe_relative_path(evidence.get("package_path"), "evidence.package_path"),
        "decision evidence",
    )
    _required_file(evidence_path, "decision evidence")
    if _file_sha256(evidence_path) != _required_sha(
        evidence.get("file_sha256"), "decision_evidence.file_sha256"
    ):
        raise ReferenceAuthorityApprovalError("Decision evidence checksum mismatch.")
    if evidence.get("attributable_sender_person_id") != authority["person_id"]:
        raise ReferenceAuthorityApprovalError(
            "Decision evidence is attributed to another person id."
        )
    _required_text(evidence.get("attributable_sender"), "attributable_sender")
    _required_text(evidence.get("attributable_recipient"), "attributable_recipient")
    _required_match(evidence.get("evidence_id"), _EVIDENCE_ID_RE, "evidence_id")
    _required_choice(evidence.get("evidence_type"), _EVIDENCE_TYPES, "evidence_type")
    decision_text, decision_at = _strict_utc(
        evidence.get("decision_at_utc"), "decision_at_utc"
    )
    _captured_text, captured_at = _strict_utc(
        evidence.get("captured_at_utc"), "captured_at_utc"
    )
    if decision_at > captured_at or captured_at > created:
        raise ReferenceAuthorityApprovalError(
            "Decision/capture/package UTC ordering is inconsistent."
        )
    if evidence.get("verification_status") != EVIDENCE_VERIFICATION_STATUS:
        raise ReferenceAuthorityApprovalError(
            "Decision evidence overstates local verification."
        )
    if evidence.get("semantic_verification_status") != SEMANTIC_VERIFICATION_STATUS:
        raise ReferenceAuthorityApprovalError(
            "Decision evidence overstates semantic verification."
        )
    _validate_evidence_suffix(evidence_path, str(evidence["evidence_type"]))

    accepted_at = _strict_utc(authority["accepted_at_utc"], "accepted_at_utc")[1]
    role_created = _strict_utc(
        human_manifest["created_at_utc"], "human_role_package.created_at_utc"
    )[1]
    if accepted_at > role_created or role_created > decision_at:
        raise ReferenceAuthorityApprovalError(
            "Reference Authority appointment was not frozen before the decision."
        )

    design_binding = _require_mapping(
        manifest.get("reserve_design_binding"), "reserve_design_binding"
    )
    design_root = _resolve_below(
        root,
        _safe_relative_path(design_binding.get("package_path"), "design.package_path"),
        "calibration reserve design package",
    )
    try:
        design_receipt = verify_calibration_reserve_design_package(design_root)
    except (CalibrationReserveError, OSError) as exc:
        raise ReferenceAuthorityApprovalError(
            f"Copied calibration reserve design is invalid: {exc}"
        ) from exc
    chosen_candidate = _find_candidate(
        design_root, str(design_binding.get("chosen_candidate_id", ""))
    )
    expected_design = {
        "decision": _required_choice(
            design_binding.get("decision"), _BINARY_DECISIONS, "reserve decision"
        ),
        "rationale": _required_text(
            design_binding.get("rationale"), "reserve rationale"
        ),
        "design_id": design_receipt["design_id"],
        "design_receipt_sha256": design_receipt["receipt_sha256"],
        "design_receipt_file_sha256": _file_sha256(
            design_root / "design_receipt.json"
        ),
        "candidate_combinations_sha256": design_receipt["outputs"]
        ["candidate_combinations"]["sha256"],
        "chosen_candidate_id": chosen_candidate["candidate_id"],
        "source_design_status": design_receipt["status"],
        "package_path": _safe_relative_path(
            design_binding.get("package_path"), "design.package_path"
        ).as_posix(),
        "changes_dataset_roles": False,
        "selects_query_ids": False,
    }
    if design_binding != expected_design:
        raise ReferenceAuthorityApprovalError(
            "Reserve-design binding differs from the copied design package."
        )
    design_created = _strict_utc(
        design_receipt["created_at_utc"], "design.created_at_utc"
    )[1]
    if design_created > decision_at:
        raise ReferenceAuthorityApprovalError(
            "Authority decision predates the reserve design."
        )
    _validate_design_event(design_root, event_id)

    derivative_decision = _validate_frozen_derivative_decision(
        root,
        manifest.get("review_derivative_decision"),
        event_id=event_id,
        decision_at=decision_at,
    )
    procedure_decision = _validate_frozen_reference_procedure(
        root, manifest.get("reference_procedure_binding")
    )
    attestations = _validate_attestations(manifest.get("authority_attestations"))
    if any(value is not True for value in attestations.values()):
        raise ReferenceAuthorityApprovalError(
            "Every fixed authority attestation must be true."
        )

    reserve_approved = expected_design["decision"] == "approved"
    procedure_approved = procedure_decision["decision"] == "approved"
    construction_authorized = reserve_approved and procedure_approved
    expected_status = APPROVED_STATUS if construction_authorized else REJECTED_STATUS
    if manifest.get("approval_status") != expected_status:
        raise ReferenceAuthorityApprovalError(
            "Approval status does not match the recorded decisions."
        )
    scope = _require_mapping(manifest.get("authorization_scope"), "authorization_scope")
    expected_scope = {
        "may_start_separate_canonical_reserve_construction": construction_authorized,
        "may_start_separate_reference_construction": construction_authorized,
        "may_include_bound_review_derivatives_in_that_next_construction": (
            construction_authorized and derivative_decision["decision"] == "approved"
        ),
        "calibration_query_selection": False,
        "calibration_execution": False,
        "review_bundle_construction": False,
        "formal_review": False,
    }
    if scope != expected_scope:
        raise ReferenceAuthorityApprovalError(
            "Authority scope exceeds or differs from the next-construction contract."
        )
    safety = _require_mapping(manifest.get("safety"), "safety")
    if set(safety) != set(_SAFETY_FALSE_FIELDS) | {
        "calibration_query_ids",
        "retest_query_ids",
    }:
        raise ReferenceAuthorityApprovalError("Authority safety fields are incomplete.")
    if any(safety.get(field) is not False for field in _SAFETY_FALSE_FIELDS):
        raise ReferenceAuthorityApprovalError(
            "Authority package has an unsafe enabled capability."
        )
    if safety.get("calibration_query_ids") != [] or safety.get("retest_query_ids") != []:
        raise ReferenceAuthorityApprovalError(
            "Authority package must not contain selected calibration/retest query ids."
        )
    if manifest.get("evidence_limitation") != _EVIDENCE_LIMITATION:
        raise ReferenceAuthorityApprovalError(
            "Authority package lost its evidence limitation."
        )
    _required_text(manifest.get("assumptions"), "assumptions")
    _required_match(package_id, _ID_RE, "package_id")
    _required_text(decision_text, "decision_at_utc")
    return manifest


def _normalize_request(payload: Mapping[str, Any]) -> dict[str, Any]:
    request = dict(payload)
    _require_exact_keys(request, _TOP_LEVEL_REQUEST_KEYS, "decision request")
    if request.get("schema") != REQUEST_SCHEMA:
        raise ReferenceAuthorityApprovalError(
            f"Request schema must be exactly {REQUEST_SCHEMA!r}."
        )
    normalized: dict[str, Any] = {
        "schema": REQUEST_SCHEMA,
        "package_id": _required_match(request.get("package_id"), _ID_RE, "package_id"),
        "event_id": _required_text(request.get("event_id"), "event_id"),
        "created_at_utc": _strict_utc(request.get("created_at_utc"), "created_at_utc")[0],
        "reference_authority_role_id": _required_match(
            request.get("reference_authority_role_id"), _ROLE_ID_RE, "reference_authority_role_id"
        ),
        "reference_authority_person_id": _required_match(
            request.get("reference_authority_person_id"), _PERSON_ID_RE, "reference_authority_person_id"
        ),
        "assumptions": _required_text(request.get("assumptions"), "assumptions"),
    }

    evidence = _require_mapping(request.get("decision_evidence"), "decision_evidence")
    _require_exact_keys(evidence, _DECISION_EVIDENCE_KEYS, "decision_evidence")
    normalized["decision_evidence"] = {
        "evidence_id": _required_match(evidence.get("evidence_id"), _EVIDENCE_ID_RE, "evidence_id"),
        "evidence_type": _required_choice(evidence.get("evidence_type"), _EVIDENCE_TYPES, "evidence_type"),
        "local_path": _safe_relative_path(evidence.get("local_path"), "evidence.local_path").as_posix(),
        "sha256": _required_sha(evidence.get("sha256"), "evidence.sha256"),
        "decision_at_utc": _strict_utc(evidence.get("decision_at_utc"), "decision_at_utc")[0],
        "captured_at_utc": _strict_utc(evidence.get("captured_at_utc"), "captured_at_utc")[0],
        "attributable_sender": _required_text(evidence.get("attributable_sender"), "attributable_sender"),
        "attributable_recipient": _required_text(evidence.get("attributable_recipient"), "attributable_recipient"),
        "attributable_sender_person_id": _required_match(
            evidence.get("attributable_sender_person_id"), _PERSON_ID_RE, "attributable_sender_person_id"
        ),
    }

    reserve = _require_mapping(request.get("reserve_design_decision"), "reserve_design_decision")
    _require_exact_keys(reserve, _RESERVE_DECISION_KEYS, "reserve_design_decision")
    normalized["reserve_design_decision"] = {
        "design_id": _required_match(reserve.get("design_id"), _ID_RE, "design_id"),
        "chosen_candidate_id": _required_match(
            reserve.get("chosen_candidate_id"), _CANDIDATE_ID_RE, "chosen_candidate_id"
        ),
        "decision": _required_choice(reserve.get("decision"), _BINARY_DECISIONS, "reserve decision"),
        "rationale": _required_text(reserve.get("rationale"), "reserve rationale"),
    }

    derivative = _require_mapping(request.get("review_derivative_decision"), "review_derivative_decision")
    _require_exact_keys(derivative, _DERIVATIVE_DECISION_KEYS, "review_derivative_decision")
    derivative_choice = _required_choice(
        derivative.get("decision"), _DERIVATIVE_DECISIONS, "derivative decision"
    )
    derivative_sha = derivative.get("receipt_sha256")
    if derivative_choice == "not_submitted":
        if derivative_sha is not None:
            raise ReferenceAuthorityApprovalError(
                "A not-submitted derivative decision cannot declare a receipt hash."
            )
    else:
        derivative_sha = _required_sha(derivative_sha, "derivative receipt_sha256")
    normalized["review_derivative_decision"] = {
        "decision": derivative_choice,
        "receipt_sha256": derivative_sha,
        "rationale": _required_text(derivative.get("rationale"), "derivative rationale"),
    }

    procedure = _require_mapping(request.get("reference_procedure_decision"), "reference_procedure_decision")
    _require_exact_keys(procedure, _PROCEDURE_DECISION_KEYS, "reference_procedure_decision")
    normalized["reference_procedure_decision"] = {
        "document_version": _required_match(
            procedure.get("document_version"), _VERSION_RE, "document_version"
        ),
        "document_sha256": _required_sha(
            procedure.get("document_sha256"), "reference procedure SHA-256"
        ),
        "decision": _required_choice(procedure.get("decision"), _BINARY_DECISIONS, "procedure decision"),
        "rationale": _required_text(procedure.get("rationale"), "procedure rationale"),
    }
    normalized["authority_attestations"] = _validate_attestations(
        request.get("authority_attestations")
    )
    return normalized


def _validate_human_role_binding(
    root: Path, request: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        manifest = validate_human_role_package(root)
    except (HumanRolePackageError, OSError) as exc:
        raise ReferenceAuthorityApprovalError(
            f"Human-role package is invalid: {exc}"
        ) from exc
    if manifest.get("event_id") != request["event_id"]:
        raise ReferenceAuthorityApprovalError(
            "Human-role package event differs from the decision request."
        )
    if manifest.get("formal_review_authorized") is not False:
        raise ReferenceAuthorityApprovalError(
            "A design decision requires a pre-calibration human-role package; formal review is already authorized."
        )
    if manifest.get("formal_review_authorization_requested") is not False:
        raise ReferenceAuthorityApprovalError(
            "A design decision requires formal_review_authorization_requested=false."
        )
    if manifest.get("calibration_receipt") is not None:
        raise ReferenceAuthorityApprovalError(
            "A design decision cannot use a human-role package that already binds calibration."
        )
    authority = _one_reference_authority(manifest)
    if authority["role_id"] != request["reference_authority_role_id"]:
        raise ReferenceAuthorityApprovalError(
            "Requested Reference Authority role id differs from the appointed role."
        )
    if authority["person_id"] != request["reference_authority_person_id"]:
        raise ReferenceAuthorityApprovalError(
            "Requested Reference Authority person id differs from the appointed person."
        )
    if request["decision_evidence"]["attributable_sender_person_id"] != authority["person_id"]:
        raise ReferenceAuthorityApprovalError(
            "Decision evidence sender person id differs from the appointed Reference Authority."
        )
    return manifest, authority


def _one_reference_authority(manifest: Mapping[str, Any]) -> dict[str, Any]:
    appointments = manifest.get("appointments")
    if not isinstance(appointments, Sequence) or isinstance(
        appointments, (str, bytes, bytearray)
    ):
        raise ReferenceAuthorityApprovalError(
            "Human-role package has no appointment array."
        )
    matches = [
        dict(row)
        for row in appointments
        if isinstance(row, Mapping)
        and row.get("role_category") == "reference_authority"
    ]
    if len(matches) != 1:
        raise ReferenceAuthorityApprovalError(
            "Human-role package must identify exactly one Reference Authority."
        )
    authority = matches[0]
    if authority.get("appointment_status") != "accepted_with_attributable_local_evidence":
        raise ReferenceAuthorityApprovalError(
            "Reference Authority does not have an evidenced accepted appointment."
        )
    return authority


def _validate_reserve_binding(
    root: Path, request: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, str]]:
    try:
        receipt = verify_calibration_reserve_design_package(root)
    except (CalibrationReserveError, OSError) as exc:
        raise ReferenceAuthorityApprovalError(
            f"Calibration reserve design package is invalid: {exc}"
        ) from exc
    decision = request["reserve_design_decision"]
    if receipt.get("design_id") != decision["design_id"]:
        raise ReferenceAuthorityApprovalError(
            "Reserve design id differs from the authority decision."
        )
    candidate = _find_candidate(root, decision["chosen_candidate_id"])
    _validate_design_event(root, request["event_id"])
    return receipt, candidate


def _find_candidate(root: Path, candidate_id: str) -> dict[str, str]:
    _required_match(candidate_id, _CANDIDATE_ID_RE, "chosen_candidate_id")
    path = _required_file(
        root / "candidate_reserve_combinations.csv", "reserve candidates"
    )
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = [dict(row) for row in csv.DictReader(handle)]
    except (OSError, csv.Error) as exc:
        raise ReferenceAuthorityApprovalError(
            f"Could not read reserve candidates: {exc}"
        ) from exc
    matches = [row for row in rows if row.get("candidate_id") == candidate_id]
    if len(matches) != 1:
        raise ReferenceAuthorityApprovalError(
            "Chosen reserve candidate id is absent or duplicated in the bound design."
        )
    if "query_region_id" in matches[0]:
        raise ReferenceAuthorityApprovalError(
            "Reserve candidate must not expose final query ids."
        )
    return matches[0]


def _validate_design_event(root: Path, event_id: str) -> None:
    path = _required_file(
        root / "authority_pending_role_allocation.csv",
        "authority-pending role allocation",
    )
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, csv.Error) as exc:
        raise ReferenceAuthorityApprovalError(
            f"Could not read authority-pending role allocation: {exc}"
        ) from exc
    events = {str(row.get("event_id", "")).strip() for row in rows}
    if events != {event_id}:
        raise ReferenceAuthorityApprovalError(
            "Calibration reserve design event differs from the decision request."
        )


def _validate_derivative_binding(
    source: Path | None, request: Mapping[str, Any]
) -> dict[str, Any] | None:
    decision = request["review_derivative_decision"]
    if source is None:
        if decision["decision"] != "not_submitted":
            raise ReferenceAuthorityApprovalError(
                "Derivative approval/rejection requires the exact lineage receipt."
            )
        return None
    if decision["decision"] == "not_submitted":
        raise ReferenceAuthorityApprovalError(
            "A supplied derivative receipt requires an explicit approved/rejected decision."
        )
    try:
        receipt = load_review_derivative_lineage_receipt(source)
    except (ReviewDerivativeLineageError, OSError) as exc:
        raise ReferenceAuthorityApprovalError(
            f"Review-derivative receipt is invalid: {exc}"
        ) from exc
    if receipt.get("receipt_sha256") != decision["receipt_sha256"]:
        raise ReferenceAuthorityApprovalError(
            "Review-derivative receipt self-hash differs from the authority decision."
        )
    if receipt.get("event_id") != request["event_id"]:
        raise ReferenceAuthorityApprovalError(
            "Review-derivative event differs from the authority decision."
        )
    return receipt


def _validate_reference_procedure(
    source: Path, request: Mapping[str, Any]
) -> None:
    expected = request["reference_procedure_decision"]["document_sha256"]
    if _file_sha256(source) != expected:
        raise ReferenceAuthorityApprovalError(
            "Reference-procedure bytes differ from the authority decision hash."
        )
    if source.stat().st_size == 0:
        raise ReferenceAuthorityApprovalError(
            "Reference-procedure document must not be empty."
        )


def _validate_decision_evidence(
    root: Path,
    request: Mapping[str, Any],
    *,
    human_manifest: Mapping[str, Any],
    authority: Mapping[str, Any],
    design_receipt: Mapping[str, Any],
    derivative: Mapping[str, Any] | None,
) -> Path:
    evidence = request["decision_evidence"]
    source = _resolve_below(
        root, Path(evidence["local_path"]), "decision evidence"
    )
    source = _required_file(source, "decision evidence")
    if source.stat().st_size == 0:
        raise ReferenceAuthorityApprovalError("Decision evidence must not be empty.")
    if _file_sha256(source) != evidence["sha256"]:
        raise ReferenceAuthorityApprovalError(
            "Decision evidence bytes differ from the declared SHA-256."
        )
    _validate_evidence_suffix(source, evidence["evidence_type"])
    decision_at = _strict_utc(evidence["decision_at_utc"], "decision_at_utc")[1]
    captured_at = _strict_utc(evidence["captured_at_utc"], "captured_at_utc")[1]
    created = _strict_utc(request["created_at_utc"], "created_at_utc")[1]
    accepted_at = _strict_utc(authority["accepted_at_utc"], "accepted_at_utc")[1]
    role_created = _strict_utc(
        human_manifest["created_at_utc"], "human_role_package.created_at_utc"
    )[1]
    design_created = _strict_utc(
        design_receipt["created_at_utc"], "design.created_at_utc"
    )[1]
    if accepted_at > role_created or role_created > decision_at:
        raise ReferenceAuthorityApprovalError(
            "Reference Authority appointment package must predate the decision."
        )
    if design_created > decision_at:
        raise ReferenceAuthorityApprovalError(
            "Authority decision cannot predate the reserve design."
        )
    if derivative is not None:
        derivative_validated = _utc_datetime(
            derivative["validated_at_utc"], "derivative.validated_at_utc"
        )
        if derivative_validated > decision_at:
            raise ReferenceAuthorityApprovalError(
                "Authority decision cannot predate the derivative receipt."
            )
    if decision_at > captured_at or captured_at > created:
        raise ReferenceAuthorityApprovalError(
            "Decision must precede capture, and capture must not postdate package creation."
        )
    return source


def _derivative_receipt_binding(
    request: Mapping[str, Any],
    derivative: Mapping[str, Any] | None,
    derivative_copy: Path | None,
    *,
    root: Path,
) -> dict[str, Any]:
    decision = request["review_derivative_decision"]
    if derivative is None:
        return {
            "decision": "not_submitted",
            "rationale": decision["rationale"],
            "package_path": None,
            "receipt_sha256": None,
            "receipt_file_sha256": None,
            "derivative_set_id": None,
            "event_id": None,
            "display_inclusion_in_next_construction": False,
            "authorizes_review_bundle": False,
        }
    if derivative_copy is None:
        raise ReferenceAuthorityApprovalError(
            "Internal derivative copy was not created."
        )
    return {
        "decision": decision["decision"],
        "rationale": decision["rationale"],
        "package_path": derivative_copy.relative_to(root).as_posix(),
        "receipt_sha256": derivative["receipt_sha256"],
        "receipt_file_sha256": _file_sha256(derivative_copy),
        "derivative_set_id": derivative["derivative_set_id"],
        "event_id": derivative["event_id"],
        "display_inclusion_in_next_construction": decision["decision"] == "approved",
        "authorizes_review_bundle": False,
    }


def _validate_frozen_derivative_decision(
    root: Path,
    value: Any,
    *,
    event_id: str,
    decision_at: datetime,
) -> dict[str, Any]:
    record = _require_mapping(value, "review_derivative_decision")
    expected_keys = {
        "decision",
        "rationale",
        "package_path",
        "receipt_sha256",
        "receipt_file_sha256",
        "derivative_set_id",
        "event_id",
        "display_inclusion_in_next_construction",
        "authorizes_review_bundle",
    }
    _require_exact_keys(record, frozenset(expected_keys), "review_derivative_decision")
    decision = _required_choice(record.get("decision"), _DERIVATIVE_DECISIONS, "derivative decision")
    _required_text(record.get("rationale"), "derivative rationale")
    if record.get("authorizes_review_bundle") is not False:
        raise ReferenceAuthorityApprovalError(
            "Derivative decision must never authorize a review bundle."
        )
    if decision == "not_submitted":
        for field in (
            "package_path",
            "receipt_sha256",
            "receipt_file_sha256",
            "derivative_set_id",
            "event_id",
        ):
            if record.get(field) is not None:
                raise ReferenceAuthorityApprovalError(
                    "Not-submitted derivative decision contains receipt metadata."
                )
        if record.get("display_inclusion_in_next_construction") is not False:
            raise ReferenceAuthorityApprovalError(
                "An absent derivative cannot be approved for inclusion."
            )
        return record
    relative = _safe_relative_path(record.get("package_path"), "derivative.package_path")
    path = _required_file(_resolve_below(root, relative, "derivative receipt"), "derivative receipt")
    if _file_sha256(path) != _required_sha(record.get("receipt_file_sha256"), "receipt_file_sha256"):
        raise ReferenceAuthorityApprovalError("Copied derivative receipt checksum mismatch.")
    try:
        receipt = load_review_derivative_lineage_receipt(path)
    except (ReviewDerivativeLineageError, OSError) as exc:
        raise ReferenceAuthorityApprovalError(f"Copied derivative receipt is invalid: {exc}") from exc
    if record.get("receipt_sha256") != receipt["receipt_sha256"]:
        raise ReferenceAuthorityApprovalError("Derivative receipt self-hash binding mismatch.")
    if record.get("derivative_set_id") != receipt["derivative_set_id"]:
        raise ReferenceAuthorityApprovalError("Derivative set id binding mismatch.")
    if record.get("event_id") != event_id or receipt["event_id"] != event_id:
        raise ReferenceAuthorityApprovalError("Derivative event binding mismatch.")
    if _utc_datetime(receipt["validated_at_utc"], "derivative.validated_at_utc") > decision_at:
        raise ReferenceAuthorityApprovalError("Authority decision predates the derivative receipt.")
    if record.get("display_inclusion_in_next_construction") is not (decision == "approved"):
        raise ReferenceAuthorityApprovalError("Derivative display-inclusion status is inconsistent.")
    return record


def _validate_frozen_reference_procedure(
    root: Path, value: Any
) -> dict[str, Any]:
    record = _require_mapping(value, "reference_procedure_binding")
    _require_exact_keys(
        record,
        frozenset(
            {"decision", "rationale", "document_version", "package_path", "file_sha256"}
        ),
        "reference_procedure_binding",
    )
    _required_choice(record.get("decision"), _BINARY_DECISIONS, "procedure decision")
    _required_text(record.get("rationale"), "procedure rationale")
    _required_match(record.get("document_version"), _VERSION_RE, "document_version")
    relative = _safe_relative_path(record.get("package_path"), "reference procedure path")
    path = _required_file(_resolve_below(root, relative, "reference procedure"), "reference procedure")
    if _file_sha256(path) != _required_sha(record.get("file_sha256"), "reference procedure hash"):
        raise ReferenceAuthorityApprovalError("Copied reference procedure checksum mismatch.")
    if path.stat().st_size == 0:
        raise ReferenceAuthorityApprovalError("Copied reference procedure is empty.")
    return record


def _validate_attestations(value: Any) -> dict[str, bool]:
    attestations = _require_mapping(value, "authority_attestations")
    _require_exact_keys(attestations, _ATTESTATION_KEYS, "authority_attestations")
    result: dict[str, bool] = {}
    for field in sorted(_ATTESTATION_KEYS):
        if attestations.get(field) is not True:
            raise ReferenceAuthorityApprovalError(
                f"Authority attestation must be true: {field}"
            )
        result[field] = True
    return result


def _copy_human_role_package(
    source_root: Path, manifest: Mapping[str, Any], target_root: Path
) -> None:
    _copy_file(source_root / "human_role_package.json", target_root / "human_role_package.json")
    evidence = manifest.get("evidence")
    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes, bytearray)):
        raise ReferenceAuthorityApprovalError("Human-role evidence list is invalid.")
    for row in evidence:
        if not isinstance(row, Mapping):
            raise ReferenceAuthorityApprovalError("Human-role evidence row is invalid.")
        relative = _safe_relative_path(row.get("package_path"), "human evidence package_path")
        _copy_file(
            _required_file(_resolve_below(source_root, relative, "human evidence"), "human evidence"),
            target_root / relative,
        )
    validate_human_role_package(target_root)


def _copy_calibration_design_package(
    source_root: Path, receipt: Mapping[str, Any], target_root: Path
) -> None:
    _copy_file(source_root / "design_receipt.json", target_root / "design_receipt.json")
    outputs = receipt.get("outputs")
    if not isinstance(outputs, Mapping):
        raise ReferenceAuthorityApprovalError("Design receipt outputs are invalid.")
    for record in outputs.values():
        if not isinstance(record, Mapping):
            raise ReferenceAuthorityApprovalError("Design output record is invalid.")
        file_name = _safe_base_name(record.get("file_name"), "design output file_name")
        _copy_file(
            _required_file(source_root / file_name, f"design output {file_name}"),
            target_root / file_name,
        )
    verify_calibration_reserve_design_package(target_root)


def _copy_file(source: Path, target: Path) -> None:
    if source.is_symlink():
        raise ReferenceAuthorityApprovalError(
            f"Symbolic-link inputs are not allowed: {source}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def _artifact_records(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise ReferenceAuthorityApprovalError(
                f"Symbolic links are not allowed in the package: {path}"
            )
        if not path.is_file() or path == root / MANIFEST_NAME:
            continue
        records.append(
            {
                "package_path": path.relative_to(root).as_posix(),
                "file_size_bytes": path.stat().st_size,
                "sha256": _file_sha256(path),
            }
        )
    return records


def _validate_artifacts(root: Path, value: Any) -> None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ReferenceAuthorityApprovalError("Artifact inventory must be an array.")
    records = list(value)
    declared_paths: list[str] = []
    for item in records:
        record = _require_mapping(item, "artifact record")
        _require_exact_keys(
            record,
            frozenset({"package_path", "file_size_bytes", "sha256"}),
            "artifact record",
        )
        relative = _safe_relative_path(record.get("package_path"), "artifact package_path")
        path = _required_file(_resolve_below(root, relative, "artifact"), "artifact")
        if path.is_symlink():
            raise ReferenceAuthorityApprovalError("Package artifacts cannot be symlinks.")
        size = record.get("file_size_bytes")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ReferenceAuthorityApprovalError("Artifact size must be a non-negative integer.")
        if path.stat().st_size != size:
            raise ReferenceAuthorityApprovalError(f"Artifact size mismatch: {relative.as_posix()}")
        if _file_sha256(path) != _required_sha(record.get("sha256"), "artifact sha256"):
            raise ReferenceAuthorityApprovalError(f"Artifact checksum mismatch: {relative.as_posix()}")
        declared_paths.append(relative.as_posix())
    if declared_paths != sorted(set(declared_paths)):
        raise ReferenceAuthorityApprovalError("Artifact inventory is duplicated or not sorted.")
    actual = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path != root / MANIFEST_NAME
    )
    if actual != declared_paths:
        raise ReferenceAuthorityApprovalError("Artifact inventory does not exactly cover package files.")


def _readme_text(payload: Mapping[str, Any]) -> str:
    status = str(payload["approval_status"])
    return (
        "# Reference Authority design decision\n\n"
        f"Package: `{payload['package_id']}`  \n"
        f"Event: `{payload['event_id']}`  \n"
        f"Status: `{status}`\n\n"
        "This immutable package binds a pre-calibration human-role package, one "
        "provisional reserve candidate, an explicit optional-derivative decision, "
        "one fixed reference procedure, and attributable local decision evidence.\n\n"
        "Even when approved, it permits only a separate canonical reserve/reference "
        "construction step. It does not assign roles, select query IDs, create "
        "reference labels, run calibration, build reviewer bundles, authorize formal "
        "review, train a model, feed FPPS, or issue a warning.\n\n"
        f"Evidence limitation: {_EVIDENCE_LIMITATION}\n"
    )


def _validate_evidence_suffix(path: Path, evidence_type: str) -> None:
    suffix = path.suffix.lower()
    allowed = {
        "email_export": {".eml", ".msg", ".mhtml"},
        "signed_pdf": {".pdf"},
        "message_export": {".html", ".mhtml", ".json", ".txt", ".pdf"},
    }
    if suffix not in allowed[evidence_type]:
        raise ReferenceAuthorityApprovalError(
            f"Decision evidence suffix {suffix!r} does not match {evidence_type!r}."
        )


def _require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ReferenceAuthorityApprovalError(f"{field} must be a JSON object.")
    return dict(value)


def _require_exact_keys(
    value: Mapping[str, Any], expected: frozenset[str], field: str
) -> None:
    actual = set(value)
    if actual != set(expected):
        raise ReferenceAuthorityApprovalError(
            f"{field} keys differ; missing={sorted(set(expected) - actual)}, "
            f"extra={sorted(actual - set(expected))}."
        )


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReferenceAuthorityApprovalError(f"{field} must be a non-blank string.")
    return value.strip()


def _required_match(value: Any, pattern: re.Pattern[str], field: str) -> str:
    text = _required_text(value, field)
    if pattern.fullmatch(text) is None:
        raise ReferenceAuthorityApprovalError(f"{field} has an invalid format: {text!r}.")
    return text


def _required_choice(value: Any, choices: frozenset[str], field: str) -> str:
    text = _required_text(value, field)
    if text not in choices:
        raise ReferenceAuthorityApprovalError(f"{field} must be one of {sorted(choices)}.")
    return text


def _required_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA_RE.fullmatch(value) is None:
        raise ReferenceAuthorityApprovalError(f"{field} must be a lowercase SHA-256 digest.")
    return value


def _strict_utc(value: Any, field: str) -> tuple[str, datetime]:
    if not isinstance(value, str) or _UTC_RE.fullmatch(value) is None:
        raise ReferenceAuthorityApprovalError(
            f"{field} must use exact YYYY-MM-DDTHH:MM:SSZ UTC format."
        )
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ReferenceAuthorityApprovalError(f"{field} is not a real UTC timestamp.") from exc
    return value, parsed


def _utc_datetime(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ReferenceAuthorityApprovalError(f"{field} must be a UTC timestamp ending in Z.")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ReferenceAuthorityApprovalError(f"{field} is not a valid UTC timestamp.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ReferenceAuthorityApprovalError(f"{field} must be UTC.")
    return parsed


def _safe_relative_path(value: Any, field: str) -> Path:
    text = _required_text(value, field).replace("\\", "/")
    pure = PurePosixPath(text)
    if (
        pure.is_absolute()
        or not pure.parts
        or any(part in {"", ".", ".."} for part in pure.parts)
        or ":" in text
    ):
        raise ReferenceAuthorityApprovalError(f"{field} must be a safe relative path.")
    return Path(*pure.parts)


def _safe_base_name(value: Any, field: str) -> str:
    text = _required_text(value, field)
    if Path(text).name != text or text in {".", ".."}:
        raise ReferenceAuthorityApprovalError(f"{field} must be a safe file name.")
    return text


def _resolve_below(root: Path, relative: Path, field: str) -> Path:
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ReferenceAuthorityApprovalError(f"{field} escapes its allowed root.") from exc
    return resolved


def _required_directory(path: str | Path, field: str) -> Path:
    candidate = Path(path)
    if not candidate.is_dir():
        raise ReferenceAuthorityApprovalError(f"{field} does not exist: {candidate}")
    if candidate.is_symlink():
        raise ReferenceAuthorityApprovalError(f"{field} cannot be a symbolic link: {candidate}")
    return candidate


def _required_file(path: str | Path, field: str) -> Path:
    candidate = Path(path)
    if not candidate.is_file():
        raise ReferenceAuthorityApprovalError(f"{field} does not exist: {candidate}")
    if candidate.is_symlink():
        raise ReferenceAuthorityApprovalError(f"{field} cannot be a symbolic link: {candidate}")
    return candidate


def _load_json_object(path: Path, field: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReferenceAuthorityApprovalError(f"Could not load {field} {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise ReferenceAuthorityApprovalError(f"{field} root must be a JSON object.")
    return dict(value)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ReferenceAuthorityApprovalError(f"Could not hash {path}: {exc}") from exc
    return digest.hexdigest()


def _canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
