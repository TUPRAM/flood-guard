"""Strict bridge receipts for qualified human-review label releases.

This module does not replace the label factory's human-role, calibration,
annotation, adjudication, consensus, QA, or labelset-freeze implementations.
It binds those existing immutable artifacts into three purpose-specific,
fail-closed receipts:

* a formal-review authorization for two genuinely independent reviewers;
* one review-pair evidence receipt per released query; and
* a qualified label-release envelope for either flood-model training or final
  model evaluation.

The builders validate supplied artifact mappings and their self-hashes. They do
not create human appointments, calibration results, legal permission,
scientific authority, reviewer decisions, or adjudications. Synthetic fixture
authority is accepted only in ``fixture_demo`` mode and is rejected by every
candidate or official-input path.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re

from floodguard.label_factory.calibration import (
    ReviewerCalibrationError,
    load_reviewer_calibration_receipt,
)
from floodguard.label_factory.human_roles import (
    HumanRolePackageError,
    validate_human_role_package,
)
from floodguard.label_factory.qualified_reference_release import (
    QUALIFIED_STATUS as QUALIFIED_REFERENCE_STATUS,
    SYNTHETIC_STATUS as SYNTHETIC_REFERENCE_STATUS,
    QualifiedReferenceReleaseError,
    load_qualified_reference_release,
    validate_qualified_reference_release,
)
from floodguard.label_factory.review_workflow import (
    ReviewWorkflowError,
    load_labelset_validation_receipt,
)
from floodguard.label_factory.versioning import (
    LabelsetVersionError,
    load_labelset_manifest,
)


FORMAL_REVIEW_AUTHORIZATION_SCHEMA = "floodguard.formal_review_authorization.v1"
REVIEW_PAIR_EVIDENCE_SCHEMA = "floodguard.review_pair_evidence_receipt.v1"
QUALIFIED_LABEL_RELEASE_SCHEMA = "floodguard.qualified_label_release.v1"

HUMAN_ROLE_PACKAGE_SCHEMA = "floodguard.human_role_package.v1"
REVIEWER_CALIBRATION_SCHEMA = "floodguard.reviewer_calibration_receipt.v1"
LABELSET_VALIDATION_SCHEMA = "floodguard.labelset_validation_receipt.v1"

DATASET_MODES = frozenset({"fixture_demo", "candidate", "official_input"})
AUTHORITY_EVIDENCE_KINDS = frozenset(
    {"synthetic_fixture_only", "production_attributable_evidence"}
)
RELEASE_PURPOSES = frozenset({"flood_model_training_labels", "model_final_evaluation"})
ROLE_CATEGORIES = (
    "reference_authority",
    "reviewer_a",
    "reviewer_b",
    "adjudicator_c",
)
REVIEWER_CATEGORIES = ("reviewer_a", "reviewer_b")
SAFE_LABEL_CODES = (0, 1, 2, 3, 4, 255)
BINARY_ELIGIBLE_CODES = (0, 1, 2)
BINARY_EXCLUDED_CODES = (3, 4, 255)

DOWNSTREAM_SAFETY_FIELDS = (
    "eligible_for_decision_layer",
    "eligible_for_access_analysis",
    "eligible_for_equity_analysis",
    "eligible_for_fpps",
    "eligible_for_action_class",
    "eligible_for_warning",
    "official_warning",
)

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PRIVATE_PATH_RE = re.compile(
    r"(?:^|[\s\"'=])(?:[A-Za-z]:[\\/]|file://|"
    r"\\\\[^\\/\s]+[\\/][^\\/\s]+|"
    r"/(?:home|Users|private|tmp|var|opt|mnt|srv|root|Volumes|data|"
    r"workspace|usr|run)(?:[\\/]|$))",
    re.IGNORECASE,
)
_ROLE_ID_RE_BY_CATEGORY = {
    "reference_authority": re.compile(r"^FG-RA-[0-9]{3,}$"),
    "reviewer_a": re.compile(r"^FG-RV-A-[0-9]{3,}$"),
    "reviewer_b": re.compile(r"^FG-RV-B-[0-9]{3,}$"),
    "adjudicator_c": re.compile(r"^FG-ADJ-C-[0-9]{3,}$"),
}


class QualifiedLabelReleaseError(ValueError):
    """Raised when a review or label-release bridge fails closed."""


def canonical_sha256(value: object) -> str:
    """Return the SHA-256 of canonical strict JSON content."""

    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise QualifiedLabelReleaseError(
            "Artifact content must be finite, canonical JSON."
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def build_formal_review_authorization(
    *,
    authorization_id: str,
    dataset_mode: str,
    release_purpose: str,
    study_area_id: str,
    human_role_package: Mapping[str, object] | str | Path,
    reviewer_calibration_receipt: Mapping[str, object] | str | Path,
    authority_evidence_kind: str,
    created_at_utc: str | datetime,
    expires_at_utc: str | datetime,
    assumptions: Sequence[str],
) -> dict[str, object]:
    """Bind an existing role package and calibration receipt for formal review.

    The supplied role package must already have its independent A/B formal gate
    open. This function does not appoint or qualify a person.
    """

    mode = _dataset_mode(dataset_mode)
    purpose = _purpose(release_purpose)
    package = _load_human_role_package(human_role_package, dataset_mode=mode)
    calibration = _load_reviewer_calibration(
        reviewer_calibration_receipt, dataset_mode=mode
    )
    package_sha = _verify_self_hash(package, "manifest_sha256", "human role package")
    calibration_sha = _verify_self_hash(
        calibration, "receipt_sha256", "reviewer calibration receipt"
    )
    roles = _validate_strict_human_roles(package)
    _validate_calibration_receipt(
        calibration,
        roles=roles,
        protocol_version=_text(package.get("protocol_version"), "protocol_version"),
        taxonomy_version=_text(package.get("taxonomy_version"), "taxonomy_version"),
    )

    evidence_kind = _authority_kind(authority_evidence_kind, mode=mode)
    _reject_fixture_authority(
        mode,
        evidence_kind=evidence_kind,
        artifacts=(package, calibration),
    )
    created = _timestamp(created_at_utc, "created_at_utc")
    expires = _timestamp(expires_at_utc, "expires_at_utc")
    not_before = _timestamp(
        calibration.get("formal_review_not_before_utc"),
        "formal_review_not_before_utc",
    )
    completed = _timestamp(
        calibration.get("calibration_completed_at_utc"),
        "calibration_completed_at_utc",
    )
    if not_before < completed:
        raise QualifiedLabelReleaseError(
            "Formal-review not-before time cannot predate calibration completion."
        )
    if created < not_before:
        raise QualifiedLabelReleaseError(
            "Formal-review authorization cannot predate its not-before gate."
        )
    if expires <= created:
        raise QualifiedLabelReleaseError(
            "Formal-review authorization expiry must follow creation."
        )

    package_binding = package.get("calibration_receipt")
    if not isinstance(package_binding, Mapping):
        raise QualifiedLabelReleaseError(
            "Human-role package lacks its copied calibration binding."
        )
    if package_binding.get("receipt_sha256") != calibration_sha:
        raise QualifiedLabelReleaseError(
            "Human-role package is bound to a different calibration receipt."
        )
    package_from = _timestamp(
        package.get("formal_review_authorized_from_utc"),
        "human-role formal_review_authorized_from_utc",
    )
    if package_from != not_before:
        raise QualifiedLabelReleaseError(
            "Human-role and calibration formal-review gates disagree."
        )

    payload: dict[str, object] = {
        "artifact_schema": FORMAL_REVIEW_AUTHORIZATION_SCHEMA,
        "authorization_id": _safe_id(authorization_id, "authorization_id"),
        "dataset_mode": mode,
        "synthetic_fixture_only": mode == "fixture_demo",
        "release_purpose": purpose,
        "event_id": _safe_id(package.get("event_id"), "event_id"),
        "study_area_id": _safe_id(study_area_id, "study_area_id"),
        "protocol_version": _text(package.get("protocol_version"), "protocol_version"),
        "taxonomy_version": _text(package.get("taxonomy_version"), "taxonomy_version"),
        "human_role_package_sha256": package_sha,
        "reviewer_calibration_receipt_sha256": calibration_sha,
        "authority_evidence_kind": evidence_kind,
        "roles": roles,
        "reviewer_ids": [
            roles[category]["role_id"] for category in REVIEWER_CATEGORIES
        ],
        "calibration_query_ids": _unique_text_array(
            calibration.get("query_region_ids"),
            "calibration query_region_ids",
            minimum=1,
        ),
        "calibration_query_manifest_sha256": _sha256(
            calibration.get("query_manifest_sha256"),
            "calibration query_manifest_sha256",
        ),
        "calibration_reference_manifest_sha256": _sha256(
            calibration.get("calibration_reference_manifest_sha256"),
            "calibration reference manifest SHA-256",
        ),
        "calibration_completed_at_utc": _iso_utc(completed),
        "formal_review_not_before_utc": _iso_utc(not_before),
        "created_at_utc": _iso_utc(created),
        "expires_at_utc": _iso_utc(expires),
        "genuinely_blinded_double_review": True,
        "formal_review_authorized": True,
        "processing_allowed": True,
        **_false_safety_fields(),
        "assumptions": _assumptions(assumptions),
    }
    payload["receipt_sha256"] = canonical_sha256(payload)
    return validate_formal_review_authorization(
        payload,
        human_role_package=package,
        reviewer_calibration_receipt=calibration,
    )


def validate_formal_review_authorization(
    receipt: Mapping[str, object],
    *,
    human_role_package: Mapping[str, object] | str | Path,
    reviewer_calibration_receipt: Mapping[str, object] | str | Path,
    verified_at_utc: str | datetime | None = None,
) -> dict[str, object]:
    """Verify a formal-review authorization and its source artifacts."""

    value = _mapping_copy(receipt, "formal-review authorization")
    expected_fields = {
        "artifact_schema",
        "authorization_id",
        "dataset_mode",
        "synthetic_fixture_only",
        "release_purpose",
        "event_id",
        "study_area_id",
        "protocol_version",
        "taxonomy_version",
        "human_role_package_sha256",
        "reviewer_calibration_receipt_sha256",
        "authority_evidence_kind",
        "roles",
        "reviewer_ids",
        "calibration_query_ids",
        "calibration_query_manifest_sha256",
        "calibration_reference_manifest_sha256",
        "calibration_completed_at_utc",
        "formal_review_not_before_utc",
        "created_at_utc",
        "expires_at_utc",
        "genuinely_blinded_double_review",
        "formal_review_authorized",
        "processing_allowed",
        *DOWNSTREAM_SAFETY_FIELDS,
        "assumptions",
        "receipt_sha256",
    }
    _exact_fields(value, expected_fields, "formal-review authorization")
    if value["artifact_schema"] != FORMAL_REVIEW_AUTHORIZATION_SCHEMA:
        raise QualifiedLabelReleaseError(
            "Unsupported formal-review authorization schema."
        )
    _verify_self_hash(value, "receipt_sha256", "formal-review authorization")
    _safe_id(value["authorization_id"], "authorization_id")
    _safe_id(value["study_area_id"], "study_area_id")
    mode = _dataset_mode(value["dataset_mode"])
    _purpose(value["release_purpose"])
    if value["synthetic_fixture_only"] is not (mode == "fixture_demo"):
        raise QualifiedLabelReleaseError(
            "Formal-review fixture disclosure is inconsistent with dataset mode."
        )
    evidence_kind = _authority_kind(value["authority_evidence_kind"], mode=mode)

    package = _load_human_role_package(human_role_package, dataset_mode=mode)
    calibration = _load_reviewer_calibration(
        reviewer_calibration_receipt, dataset_mode=mode
    )
    package_sha = _verify_self_hash(package, "manifest_sha256", "human role package")
    calibration_sha = _verify_self_hash(
        calibration, "receipt_sha256", "reviewer calibration receipt"
    )
    if (
        value["human_role_package_sha256"] != package_sha
        or value["reviewer_calibration_receipt_sha256"] != calibration_sha
    ):
        raise QualifiedLabelReleaseError(
            "Formal-review authorization source hashes were substituted."
        )
    roles = _validate_strict_human_roles(package)
    if value["roles"] != roles:
        raise QualifiedLabelReleaseError(
            "Formal-review authorization role identities were substituted."
        )
    _validate_calibration_receipt(
        calibration,
        roles=roles,
        protocol_version=_text(value["protocol_version"], "protocol_version"),
        taxonomy_version=_text(value["taxonomy_version"], "taxonomy_version"),
    )
    expected_reviewers = [
        roles[category]["role_id"] for category in REVIEWER_CATEGORIES
    ]
    if value["reviewer_ids"] != expected_reviewers:
        raise QualifiedLabelReleaseError(
            "Formal-review authorization reviewer IDs were substituted."
        )
    if value["event_id"] != package.get("event_id"):
        raise QualifiedLabelReleaseError(
            "Formal-review authorization event differs from the role package."
        )
    if value["protocol_version"] != package.get("protocol_version") or value[
        "taxonomy_version"
    ] != package.get("taxonomy_version"):
        raise QualifiedLabelReleaseError(
            "Formal-review protocol or taxonomy differs from the role package."
        )
    package_binding = package.get("calibration_receipt")
    if (
        not isinstance(package_binding, Mapping)
        or package_binding.get("receipt_sha256") != calibration_sha
    ):
        raise QualifiedLabelReleaseError(
            "Human-role package is not bound to the supplied calibration receipt."
        )
    if (
        value["calibration_query_ids"]
        != _unique_text_array(
            calibration.get("query_region_ids"),
            "calibration query_region_ids",
            minimum=1,
        )
        or value["calibration_query_manifest_sha256"]
        != calibration.get("query_manifest_sha256")
        or value["calibration_reference_manifest_sha256"]
        != calibration.get("calibration_reference_manifest_sha256")
    ):
        raise QualifiedLabelReleaseError(
            "Formal-review calibration lineage was substituted."
        )
    completed = _timestamp(
        value["calibration_completed_at_utc"],
        "calibration_completed_at_utc",
    )
    not_before = _timestamp(
        value["formal_review_not_before_utc"],
        "formal_review_not_before_utc",
    )
    created = _timestamp(value["created_at_utc"], "created_at_utc")
    expires = _timestamp(value["expires_at_utc"], "expires_at_utc")
    if (
        _iso_utc(completed) != calibration.get("calibration_completed_at_utc")
        or _iso_utc(not_before) != calibration.get("formal_review_not_before_utc")
        or package.get("formal_review_authorized_from_utc") != _iso_utc(not_before)
        or not_before < completed
        or created < not_before
        or expires <= created
    ):
        raise QualifiedLabelReleaseError(
            "Formal-review authorization chronology is invalid."
        )
    if verified_at_utc is not None:
        verified = _timestamp(verified_at_utc, "verified_at_utc")
        if not created <= verified <= expires:
            raise QualifiedLabelReleaseError(
                "Formal-review authorization is not valid at verification time."
            )
    if (
        value["genuinely_blinded_double_review"] is not True
        or value["formal_review_authorized"] is not True
        or value["processing_allowed"] is not True
    ):
        raise QualifiedLabelReleaseError(
            "Formal-review authorization gate is not open."
        )
    _require_false_safety(value, "formal-review authorization")
    _assumptions(value["assumptions"])
    _reject_fixture_authority(
        mode,
        evidence_kind=evidence_kind,
        artifacts=(package, calibration, value),
    )
    return value


def build_review_pair_evidence_receipt(
    *,
    pair_id: str,
    formal_review_authorization: Mapping[str, object],
    human_role_package: Mapping[str, object] | str | Path,
    reviewer_calibration_receipt: Mapping[str, object] | str | Path,
    reviewer_a_annotation: Mapping[str, object],
    reviewer_b_annotation: Mapping[str, object],
    reviewer_a_bundle_sha256: str,
    reviewer_b_bundle_sha256: str,
    reviewer_a_evidence_set_sha256: str,
    reviewer_b_evidence_set_sha256: str,
    agreement_evidence_sha256: str,
    consensus_receipt_sha256: str,
    reveal_at_utc: str | datetime,
    adjudication: Mapping[str, object] | None = None,
    assumptions: Sequence[str] = (),
) -> dict[str, object]:
    """Bind one independently reviewed A/B pair and optional adjudication."""

    authorization = validate_formal_review_authorization(
        formal_review_authorization,
        human_role_package=human_role_package,
        reviewer_calibration_receipt=reviewer_calibration_receipt,
    )
    annotation_a = _mapping_copy(reviewer_a_annotation, "reviewer A annotation")
    annotation_b = _mapping_copy(reviewer_b_annotation, "reviewer B annotation")
    annotations = _validate_annotation_pair(
        annotation_a,
        annotation_b,
        authorization=authorization,
        bundle_sha_by_category={
            "reviewer_a": reviewer_a_bundle_sha256,
            "reviewer_b": reviewer_b_bundle_sha256,
        },
    )
    evidence_a = _sha256(
        reviewer_a_evidence_set_sha256, "reviewer A evidence-set SHA-256"
    )
    evidence_b = _sha256(
        reviewer_b_evidence_set_sha256, "reviewer B evidence-set SHA-256"
    )
    if evidence_a != evidence_b:
        raise QualifiedLabelReleaseError(
            "Independent reviewers received different review evidence sets."
        )
    reveal = _timestamp(reveal_at_utc, "reveal_at_utc")
    latest_lock = max(annotations["locked_at_by_reviewer"].values())
    if reveal < latest_lock or reveal > _timestamp(
        authorization["expires_at_utc"], "formal review expiry"
    ):
        raise QualifiedLabelReleaseError(
            "Pair evidence reveal must follow both locks within authorization."
        )

    disagreement_reasons = _pair_disagreement_reasons(annotation_a, annotation_b)
    adjudication_summary = _validate_adjudication(
        adjudication,
        annotation_a=annotation_a,
        annotation_b=annotation_b,
        adjudicator_id=authorization["roles"]["adjudicator_c"]["role_id"],
        reveal_at_utc=reveal,
        disagreement_reasons=disagreement_reasons,
        consensus_receipt_sha256=_sha256(
            consensus_receipt_sha256, "consensus receipt SHA-256"
        ),
    )
    if adjudication_summary is None:
        outcome = "paired_agreement_locked"
    elif adjudication_summary["outcome"] == "reject":
        outcome = "excluded_rejected"
    else:
        outcome = "adjudicated_locked"

    payload: dict[str, object] = {
        "artifact_schema": REVIEW_PAIR_EVIDENCE_SCHEMA,
        "pair_id": _safe_id(pair_id, "pair_id"),
        "dataset_mode": authorization["dataset_mode"],
        "synthetic_fixture_only": authorization["synthetic_fixture_only"],
        "release_purpose": authorization["release_purpose"],
        "event_id": annotation_a["event_id"],
        "study_area_id": authorization["study_area_id"],
        "tile_id": annotation_a["tile_id"],
        "query_region_id": annotation_a["query_region_id"],
        "formal_review_authorization_sha256": authorization["receipt_sha256"],
        "human_role_package_sha256": authorization["human_role_package_sha256"],
        "reviewer_ids": authorization["reviewer_ids"],
        "reviewer_annotation_ids": {
            "reviewer_a": annotation_a["annotation_id"],
            "reviewer_b": annotation_b["annotation_id"],
        },
        "reviewer_annotation_sha256": {
            "reviewer_a": canonical_sha256(annotation_a),
            "reviewer_b": canonical_sha256(annotation_b),
        },
        "reviewer_bundle_sha256": {
            "reviewer_a": _sha256(
                reviewer_a_bundle_sha256, "reviewer A bundle SHA-256"
            ),
            "reviewer_b": _sha256(
                reviewer_b_bundle_sha256, "reviewer B bundle SHA-256"
            ),
        },
        "reviewer_evidence_set_sha256": {
            "reviewer_a": evidence_a,
            "reviewer_b": evidence_b,
        },
        "review_evidence_set_sha256": evidence_a,
        "grid_contract_sha256": annotations["grid_contract_sha256"],
        "source_registry_sha256": annotations["source_registry_sha256"],
        "context_manifest_sha256": annotations["context_manifest_sha256"],
        "locked_at_by_reviewer": {
            category: _iso_utc(value)
            for category, value in annotations["locked_at_by_reviewer"].items()
        },
        "reveal_at_utc": _iso_utc(reveal),
        "model_predictions_visible": False,
        "other_reviewer_annotations_visible": False,
        "disagreement_reasons": list(disagreement_reasons),
        "agreement_evidence_sha256": _sha256(
            agreement_evidence_sha256, "agreement evidence SHA-256"
        ),
        "consensus_receipt_sha256": _sha256(
            consensus_receipt_sha256, "consensus receipt SHA-256"
        ),
        "adjudication": adjudication_summary,
        "pair_outcome": outcome,
        "eligible_for_label_release": outcome != "excluded_rejected",
        "processing_allowed": outcome != "excluded_rejected",
        **_false_safety_fields(),
        "assumptions": _assumptions(assumptions),
    }
    payload["receipt_sha256"] = canonical_sha256(payload)
    return validate_review_pair_evidence_receipt(
        payload,
        formal_review_authorization=authorization,
        human_role_package=human_role_package,
        reviewer_calibration_receipt=reviewer_calibration_receipt,
        reviewer_a_annotation=annotation_a,
        reviewer_b_annotation=annotation_b,
        adjudication=adjudication,
    )


def validate_review_pair_evidence_receipt(
    receipt: Mapping[str, object],
    *,
    formal_review_authorization: Mapping[str, object],
    human_role_package: Mapping[str, object] | str | Path,
    reviewer_calibration_receipt: Mapping[str, object] | str | Path,
    reviewer_a_annotation: Mapping[str, object],
    reviewer_b_annotation: Mapping[str, object],
    adjudication: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Verify a pair receipt against exact role, calibration, and review evidence."""

    value = _mapping_copy(receipt, "review-pair evidence receipt")
    expected_fields = {
        "artifact_schema",
        "pair_id",
        "dataset_mode",
        "synthetic_fixture_only",
        "release_purpose",
        "event_id",
        "study_area_id",
        "tile_id",
        "query_region_id",
        "formal_review_authorization_sha256",
        "human_role_package_sha256",
        "reviewer_ids",
        "reviewer_annotation_ids",
        "reviewer_annotation_sha256",
        "reviewer_bundle_sha256",
        "reviewer_evidence_set_sha256",
        "review_evidence_set_sha256",
        "grid_contract_sha256",
        "source_registry_sha256",
        "context_manifest_sha256",
        "locked_at_by_reviewer",
        "reveal_at_utc",
        "model_predictions_visible",
        "other_reviewer_annotations_visible",
        "disagreement_reasons",
        "agreement_evidence_sha256",
        "consensus_receipt_sha256",
        "adjudication",
        "pair_outcome",
        "eligible_for_label_release",
        "processing_allowed",
        *DOWNSTREAM_SAFETY_FIELDS,
        "assumptions",
        "receipt_sha256",
    }
    _exact_fields(value, expected_fields, "review-pair evidence receipt")
    if value["artifact_schema"] != REVIEW_PAIR_EVIDENCE_SCHEMA:
        raise QualifiedLabelReleaseError("Unsupported review-pair evidence schema.")
    _verify_self_hash(value, "receipt_sha256", "review-pair evidence receipt")
    _safe_id(value["pair_id"], "pair_id")
    authorization = validate_formal_review_authorization(
        formal_review_authorization,
        human_role_package=human_role_package,
        reviewer_calibration_receipt=reviewer_calibration_receipt,
    )
    if (
        value["formal_review_authorization_sha256"] != authorization["receipt_sha256"]
        or value["human_role_package_sha256"]
        != authorization["human_role_package_sha256"]
        or value["dataset_mode"] != authorization["dataset_mode"]
        or value["synthetic_fixture_only"]
        is not authorization["synthetic_fixture_only"]
        or value["release_purpose"] != authorization["release_purpose"]
        or value["study_area_id"] != authorization["study_area_id"]
        or value["reviewer_ids"] != authorization["reviewer_ids"]
    ):
        raise QualifiedLabelReleaseError(
            "Review-pair authorization lineage was substituted."
        )
    annotation_a = _mapping_copy(reviewer_a_annotation, "reviewer A annotation")
    annotation_b = _mapping_copy(reviewer_b_annotation, "reviewer B annotation")
    bundle_hashes = _sha_mapping(
        value["reviewer_bundle_sha256"],
        expected_keys={"reviewer_a", "reviewer_b"},
        label="reviewer bundle hashes",
    )
    annotations = _validate_annotation_pair(
        annotation_a,
        annotation_b,
        authorization=authorization,
        bundle_sha_by_category=bundle_hashes,
    )
    expected_identity = {
        "event_id": annotation_a["event_id"],
        "tile_id": annotation_a["tile_id"],
        "query_region_id": annotation_a["query_region_id"],
        "grid_contract_sha256": annotations["grid_contract_sha256"],
        "source_registry_sha256": annotations["source_registry_sha256"],
        "context_manifest_sha256": annotations["context_manifest_sha256"],
    }
    for field, expected in expected_identity.items():
        if value[field] != expected:
            raise QualifiedLabelReleaseError(f"Review-pair {field} was substituted.")
    expected_ids = {
        "reviewer_a": annotation_a["annotation_id"],
        "reviewer_b": annotation_b["annotation_id"],
    }
    expected_hashes = {
        "reviewer_a": canonical_sha256(annotation_a),
        "reviewer_b": canonical_sha256(annotation_b),
    }
    if (
        value["reviewer_annotation_ids"] != expected_ids
        or value["reviewer_annotation_sha256"] != expected_hashes
    ):
        raise QualifiedLabelReleaseError(
            "Review-pair annotation identity or content was substituted."
        )
    evidence_hashes = _sha_mapping(
        value["reviewer_evidence_set_sha256"],
        expected_keys={"reviewer_a", "reviewer_b"},
        label="reviewer evidence-set hashes",
    )
    common_evidence_sha = _sha256(
        value["review_evidence_set_sha256"], "review evidence-set SHA-256"
    )
    if (
        evidence_hashes["reviewer_a"] != evidence_hashes["reviewer_b"]
        or evidence_hashes["reviewer_a"] != common_evidence_sha
    ):
        raise QualifiedLabelReleaseError(
            "Independent reviewers did not receive an identical evidence set."
        )
    locked_mapping = value["locked_at_by_reviewer"]
    if not isinstance(locked_mapping, Mapping) or set(locked_mapping) != {
        "reviewer_a",
        "reviewer_b",
    }:
        raise QualifiedLabelReleaseError(
            "Review-pair lock mapping must cover exactly A and B."
        )
    expected_locks = {
        category: _iso_utc(locked)
        for category, locked in annotations["locked_at_by_reviewer"].items()
    }
    if dict(locked_mapping) != expected_locks:
        raise QualifiedLabelReleaseError(
            "Review-pair lock timestamps were substituted."
        )
    reveal = _timestamp(value["reveal_at_utc"], "reveal_at_utc")
    if reveal < max(
        annotations["locked_at_by_reviewer"].values()
    ) or reveal > _timestamp(authorization["expires_at_utc"], "formal review expiry"):
        raise QualifiedLabelReleaseError(
            "Review-pair reveal is outside the authorized post-lock window."
        )
    if (
        value["model_predictions_visible"] is not False
        or value["other_reviewer_annotations_visible"] is not False
    ):
        raise QualifiedLabelReleaseError(
            "Review-pair receipt contains a blinding breach."
        )
    reasons = _pair_disagreement_reasons(annotation_a, annotation_b)
    if value["disagreement_reasons"] != list(reasons):
        raise QualifiedLabelReleaseError(
            "Review-pair disagreement reasons were substituted."
        )
    consensus_sha = _sha256(
        value["consensus_receipt_sha256"], "consensus receipt SHA-256"
    )
    expected_adjudication = _validate_adjudication(
        adjudication,
        annotation_a=annotation_a,
        annotation_b=annotation_b,
        adjudicator_id=authorization["roles"]["adjudicator_c"]["role_id"],
        reveal_at_utc=reveal,
        disagreement_reasons=reasons,
        consensus_receipt_sha256=consensus_sha,
    )
    if value["adjudication"] != expected_adjudication:
        raise QualifiedLabelReleaseError(
            "Review-pair adjudication lineage was substituted."
        )
    expected_outcome = (
        "paired_agreement_locked"
        if expected_adjudication is None
        else (
            "excluded_rejected"
            if expected_adjudication["outcome"] == "reject"
            else "adjudicated_locked"
        )
    )
    if value["pair_outcome"] != expected_outcome:
        raise QualifiedLabelReleaseError(
            "Review-pair outcome is inconsistent with adjudication."
        )
    eligible = expected_outcome != "excluded_rejected"
    if (
        value["eligible_for_label_release"] is not eligible
        or value["processing_allowed"] is not eligible
    ):
        raise QualifiedLabelReleaseError(
            "Review-pair eligibility is inconsistent with its outcome."
        )
    _sha256(value["agreement_evidence_sha256"], "agreement evidence SHA-256")
    _require_false_safety(value, "review-pair evidence receipt")
    _assumptions(value["assumptions"])
    return value


def build_qualified_label_release(
    *,
    release_id: str,
    purpose: str,
    formal_review_authorization: Mapping[str, object],
    human_role_package: Mapping[str, object] | str | Path,
    reviewer_calibration_receipt: Mapping[str, object] | str | Path,
    labelset_manifest: Mapping[str, object] | str | Path,
    labelset_validation_receipt: Mapping[str, object] | str | Path,
    review_pair_receipts: Sequence[Mapping[str, object]],
    qualified_reference_release_receipt: Mapping[str, object] | str | Path,
    qa_receipt_sha256: str,
    agreement_evidence_sha256: str,
    raster_lineage_sha256: str,
    consensus_receipt_sha256: str,
    adjudication_import_receipt_sha256: str,
    class_counts: Mapping[int | str, int],
    created_at_utc: str | datetime,
    assumptions: Sequence[str],
) -> dict[str, object]:
    """Create a purpose-specific envelope over an existing frozen labelset."""

    authorization = validate_formal_review_authorization(
        formal_review_authorization,
        human_role_package=human_role_package,
        reviewer_calibration_receipt=reviewer_calibration_receipt,
    )
    release_purpose = _purpose(purpose)
    if release_purpose != authorization["release_purpose"]:
        raise QualifiedLabelReleaseError(
            "Release purpose differs from its pre-review authorization."
        )
    if authorization["dataset_mode"] != "fixture_demo":
        raise QualifiedLabelReleaseError(
            "Candidate/official qualified-label release v1 is blocked until a "
            "canonical attributable signed release-authority receipt validator "
            "is available."
        )
    labelset = _load_labelset_manifest(
        labelset_manifest, dataset_mode=str(authorization["dataset_mode"])
    )
    validation = _load_labelset_validation(
        labelset_validation_receipt,
        dataset_mode=str(authorization["dataset_mode"]),
    )
    labelset_sha = _verify_self_hash(labelset, "manifest_sha256", "labelset manifest")
    validation_sha = _verify_self_hash(
        validation, "receipt_sha256", "labelset validation receipt"
    )
    _validate_labelset_validation(
        labelset,
        validation,
        authorization=authorization,
    )
    reference = _load_qualified_reference_release(qualified_reference_release_receipt)
    reference_purpose = _validate_reference_compatibility(
        reference,
        authorization=authorization,
        release_purpose=release_purpose,
    )
    counts = _class_counts(class_counts)
    binary_count = sum(counts[str(code)] for code in BINARY_ELIGIBLE_CODES)
    excluded_count = sum(counts[str(code)] for code in BINARY_EXCLUDED_CODES)
    if release_purpose == "flood_model_training_labels":
        if counts["1"] == 0 or counts["0"] + counts["2"] == 0:
            raise QualifiedLabelReleaseError(
                "Training release requires positive and explicit negative labels."
            )

    pair_values = [
        _validate_pair_envelope(pair, authorization=authorization)
        for pair in review_pair_receipts
    ]
    if not pair_values:
        raise QualifiedLabelReleaseError(
            "Qualified label release requires review-pair evidence."
        )
    if any(pair["eligible_for_label_release"] is not True for pair in pair_values):
        raise QualifiedLabelReleaseError(
            "Rejected or contaminated review pairs cannot enter a label release."
        )
    query_ids = [str(pair["query_region_id"]) for pair in pair_values]
    if len(query_ids) != len(set(query_ids)):
        raise QualifiedLabelReleaseError(
            "Qualified label release contains duplicate query pairs."
        )
    expected_queries = _unique_text_array(
        validation.get("query_region_ids"),
        "labelset validation query_region_ids",
        minimum=1,
    )
    if set(query_ids) != set(expected_queries):
        raise QualifiedLabelReleaseError(
            "Review-pair evidence must exactly cover the validated labelset queries."
        )
    agreement_sha = _sha256(agreement_evidence_sha256, "agreement evidence SHA-256")
    if validation["agreement_evidence_sha256"] != agreement_sha:
        raise QualifiedLabelReleaseError(
            "Labelset validation and release agreement evidence differ."
        )
    raster_sha = _sha256(raster_lineage_sha256, "raster lineage SHA-256")
    if validation["raster_lineage_sha256"] != raster_sha:
        raise QualifiedLabelReleaseError(
            "Labelset validation and release raster lineage differ."
        )
    consensus_sha = _sha256(consensus_receipt_sha256, "consensus receipt SHA-256")
    adjudication_sha = _sha256(
        adjudication_import_receipt_sha256,
        "adjudication import receipt SHA-256",
    )
    for pair in pair_values:
        if (
            pair["agreement_evidence_sha256"] != agreement_sha
            or pair["consensus_receipt_sha256"] != consensus_sha
        ):
            raise QualifiedLabelReleaseError(
                "Review-pair agreement or consensus lineage differs from the release."
            )
        pair_adjudication = pair["adjudication"]
        if (
            pair_adjudication is not None
            and pair_adjudication["adjudication_import_receipt_sha256"]
            != adjudication_sha
        ):
            raise QualifiedLabelReleaseError(
                "Review-pair adjudication import differs from the release."
            )

    created = _timestamp(created_at_utc, "created_at_utc")
    latest_lineage_time = max(
        _timestamp(
            authorization["created_at_utc"],
            "formal authorization created_at_utc",
        ),
        _timestamp(reference["generated_at"], "qualified reference generated_at"),
        _timestamp(labelset.get("created_at_utc"), "labelset created_at_utc"),
        _timestamp(
            validation.get("validated_at_utc"),
            "labelset validation validated_at_utc",
        ),
        *(_latest_pair_time(pair) for pair in pair_values),
    )
    if created < latest_lineage_time:
        raise QualifiedLabelReleaseError(
            "Qualified label release predates review, adjudication, labelset, "
            "reference, or validation evidence."
        )
    training_eligible = release_purpose == "flood_model_training_labels"
    evaluation_eligible = release_purpose == "model_final_evaluation"
    purpose_binding_sha = canonical_sha256(
        {
            "release_purpose": release_purpose,
            "formal_review_authorization_sha256": authorization["receipt_sha256"],
            "labelset_manifest_sha256": labelset_sha,
            "labelset_validation_receipt_sha256": validation_sha,
            "label_content_sha256": labelset["label_content_sha256"],
            "query_region_ids": sorted(query_ids),
            "review_pair_receipt_sha256_by_query": {
                str(pair["query_region_id"]): str(pair["receipt_sha256"])
                for pair in sorted(
                    pair_values, key=lambda item: str(item["query_region_id"])
                )
            },
        }
    )
    payload: dict[str, object] = {
        "artifact_schema": QUALIFIED_LABEL_RELEASE_SCHEMA,
        "release_id": _safe_id(release_id, "release_id"),
        "dataset_mode": authorization["dataset_mode"],
        "synthetic_fixture_only": authorization["synthetic_fixture_only"],
        "event_id": authorization["event_id"],
        "study_area_id": authorization["study_area_id"],
        "purpose": release_purpose,
        "qualified_reference_purpose": release_purpose,
        "qualified_reference_authorized_purpose": reference_purpose,
        "qualified_reference_release_id": reference["release_id"],
        "qualified_reference_release_status": reference["release_status"],
        "qualified_reference_receipt_sha256": reference["release_sha256"],
        "release_authority_status": "not_applicable_synthetic_fixture",
        "release_authority_receipt_sha256": None,
        "release_authority_signature_verified": False,
        "confers_release_authority": False,
        "formal_review_authorization_sha256": authorization["receipt_sha256"],
        "human_role_package_sha256": authorization["human_role_package_sha256"],
        "reviewer_calibration_receipt_sha256": authorization[
            "reviewer_calibration_receipt_sha256"
        ],
        "labelset_id": _text(labelset.get("labelset_id"), "labelset_id"),
        "labelset_manifest_sha256": labelset_sha,
        "labelset_validation_receipt_sha256": validation_sha,
        "labelset_purpose_binding_sha256": purpose_binding_sha,
        "label_content_sha256": _sha256(
            labelset.get("label_content_sha256"), "label content SHA-256"
        ),
        "review_pair_receipt_sha256_by_query": {
            str(pair["query_region_id"]): str(pair["receipt_sha256"])
            for pair in sorted(
                pair_values, key=lambda item: str(item["query_region_id"])
            )
        },
        "query_region_ids": sorted(query_ids),
        "qa_receipt_sha256": _sha256(qa_receipt_sha256, "QA receipt SHA-256"),
        "agreement_evidence_sha256": agreement_sha,
        "raster_lineage_sha256": raster_sha,
        "consensus_receipt_sha256": consensus_sha,
        "adjudication_import_receipt_sha256": adjudication_sha,
        "class_counts": counts,
        "binary_eligible_codes": list(BINARY_ELIGIBLE_CODES),
        "binary_excluded_codes": list(BINARY_EXCLUDED_CODES),
        "binary_eligible_cell_count": binary_count,
        "binary_excluded_cell_count": excluded_count,
        "unknown_cells_preserved": True,
        "eligible_for_query_model_training": training_eligible,
        "eligible_for_flood_model_training": training_eligible,
        "eligible_for_model_evaluation": evaluation_eligible,
        "processing_allowed": True,
        **_false_safety_fields(),
        "created_at_utc": _iso_utc(created),
        "assumptions": _assumptions(assumptions),
    }
    payload["release_sha256"] = canonical_sha256(payload)
    return validate_qualified_label_release(
        payload,
        formal_review_authorization=authorization,
        human_role_package=human_role_package,
        reviewer_calibration_receipt=reviewer_calibration_receipt,
        labelset_manifest=labelset,
        labelset_validation_receipt=validation,
        review_pair_receipts=pair_values,
        qualified_reference_release_receipt=reference,
    )


def validate_qualified_label_release(
    release: Mapping[str, object],
    *,
    formal_review_authorization: Mapping[str, object],
    human_role_package: Mapping[str, object] | str | Path,
    reviewer_calibration_receipt: Mapping[str, object] | str | Path,
    labelset_manifest: Mapping[str, object] | str | Path,
    labelset_validation_receipt: Mapping[str, object] | str | Path,
    review_pair_receipts: Sequence[Mapping[str, object]],
    qualified_reference_release_receipt: Mapping[str, object] | str | Path,
) -> dict[str, object]:
    """Verify a qualified label release and its bridge receipts."""

    value = _mapping_copy(release, "qualified label release")
    expected_fields = {
        "artifact_schema",
        "release_id",
        "dataset_mode",
        "synthetic_fixture_only",
        "event_id",
        "study_area_id",
        "purpose",
        "qualified_reference_purpose",
        "qualified_reference_authorized_purpose",
        "qualified_reference_release_id",
        "qualified_reference_release_status",
        "qualified_reference_receipt_sha256",
        "release_authority_status",
        "release_authority_receipt_sha256",
        "release_authority_signature_verified",
        "confers_release_authority",
        "formal_review_authorization_sha256",
        "human_role_package_sha256",
        "reviewer_calibration_receipt_sha256",
        "labelset_id",
        "labelset_manifest_sha256",
        "labelset_validation_receipt_sha256",
        "labelset_purpose_binding_sha256",
        "label_content_sha256",
        "review_pair_receipt_sha256_by_query",
        "query_region_ids",
        "qa_receipt_sha256",
        "agreement_evidence_sha256",
        "raster_lineage_sha256",
        "consensus_receipt_sha256",
        "adjudication_import_receipt_sha256",
        "class_counts",
        "binary_eligible_codes",
        "binary_excluded_codes",
        "binary_eligible_cell_count",
        "binary_excluded_cell_count",
        "unknown_cells_preserved",
        "eligible_for_query_model_training",
        "eligible_for_flood_model_training",
        "eligible_for_model_evaluation",
        "processing_allowed",
        *DOWNSTREAM_SAFETY_FIELDS,
        "created_at_utc",
        "assumptions",
        "release_sha256",
    }
    _exact_fields(value, expected_fields, "qualified label release")
    if value["artifact_schema"] != QUALIFIED_LABEL_RELEASE_SCHEMA:
        raise QualifiedLabelReleaseError("Unsupported qualified label-release schema.")
    _verify_self_hash(value, "release_sha256", "qualified label release")
    _safe_id(value["release_id"], "release_id")
    purpose = _purpose(value["purpose"])
    if value["qualified_reference_purpose"] != purpose:
        raise QualifiedLabelReleaseError(
            "Qualified-reference purpose differs from label-release purpose."
        )
    authorization = validate_formal_review_authorization(
        formal_review_authorization,
        human_role_package=human_role_package,
        reviewer_calibration_receipt=reviewer_calibration_receipt,
    )
    if purpose != authorization["release_purpose"]:
        raise QualifiedLabelReleaseError(
            "Qualified release purpose differs from pre-review authorization."
        )
    if authorization["dataset_mode"] != "fixture_demo":
        raise QualifiedLabelReleaseError(
            "Candidate/official qualified-label release v1 is blocked until a "
            "canonical attributable signed release-authority receipt validator "
            "is available."
        )
    if (
        value["release_authority_status"] != "not_applicable_synthetic_fixture"
        or value["release_authority_receipt_sha256"] is not None
        or value["release_authority_signature_verified"] is not False
        or value["confers_release_authority"] is not False
    ):
        raise QualifiedLabelReleaseError(
            "Synthetic fixture release cannot claim release authority."
        )
    reference = _load_qualified_reference_release(qualified_reference_release_receipt)
    authorized_reference_purpose = _validate_reference_compatibility(
        reference,
        authorization=authorization,
        release_purpose=purpose,
    )
    if (
        value["qualified_reference_authorized_purpose"] != authorized_reference_purpose
        or value["qualified_reference_release_id"] != reference["release_id"]
        or value["qualified_reference_release_status"] != reference["release_status"]
        or value["qualified_reference_receipt_sha256"] != reference["release_sha256"]
    ):
        raise QualifiedLabelReleaseError(
            "Qualified-reference release identity or purpose was substituted."
        )
    expected_authorization = {
        "dataset_mode": authorization["dataset_mode"],
        "synthetic_fixture_only": authorization["synthetic_fixture_only"],
        "event_id": authorization["event_id"],
        "study_area_id": authorization["study_area_id"],
        "formal_review_authorization_sha256": authorization["receipt_sha256"],
        "human_role_package_sha256": authorization["human_role_package_sha256"],
        "reviewer_calibration_receipt_sha256": authorization[
            "reviewer_calibration_receipt_sha256"
        ],
    }
    for field, expected in expected_authorization.items():
        if value[field] != expected:
            raise QualifiedLabelReleaseError(
                f"Qualified label-release {field} was substituted."
            )
    labelset = _load_labelset_manifest(
        labelset_manifest, dataset_mode=str(authorization["dataset_mode"])
    )
    validation = _load_labelset_validation(
        labelset_validation_receipt,
        dataset_mode=str(authorization["dataset_mode"]),
    )
    labelset_sha = _verify_self_hash(labelset, "manifest_sha256", "labelset manifest")
    validation_sha = _verify_self_hash(
        validation, "receipt_sha256", "labelset validation receipt"
    )
    _validate_labelset_validation(
        labelset,
        validation,
        authorization=authorization,
    )
    expected_labelset = {
        "labelset_id": labelset.get("labelset_id"),
        "labelset_manifest_sha256": labelset_sha,
        "labelset_validation_receipt_sha256": validation_sha,
        "label_content_sha256": labelset.get("label_content_sha256"),
    }
    for field, expected in expected_labelset.items():
        if value[field] != expected:
            raise QualifiedLabelReleaseError(
                f"Qualified label-release {field} was substituted."
            )
    pairs = [
        _validate_pair_envelope(pair, authorization=authorization)
        for pair in review_pair_receipts
    ]
    if not pairs or any(
        pair["eligible_for_label_release"] is not True for pair in pairs
    ):
        raise QualifiedLabelReleaseError(
            "Qualified release contains no usable pairs or an excluded pair."
        )
    expected_pair_hashes = {
        str(pair["query_region_id"]): str(pair["receipt_sha256"])
        for pair in sorted(pairs, key=lambda item: str(item["query_region_id"]))
    }
    if value["review_pair_receipt_sha256_by_query"] != expected_pair_hashes:
        raise QualifiedLabelReleaseError(
            "Qualified label-release pair evidence was substituted."
        )
    expected_queries = sorted(expected_pair_hashes)
    if value["query_region_ids"] != expected_queries or set(expected_queries) != set(
        _unique_text_array(
            validation.get("query_region_ids"),
            "labelset validation query_region_ids",
            minimum=1,
        )
    ):
        raise QualifiedLabelReleaseError(
            "Qualified label-release query coverage differs from validation."
        )
    expected_purpose_binding = canonical_sha256(
        {
            "release_purpose": purpose,
            "formal_review_authorization_sha256": authorization["receipt_sha256"],
            "labelset_manifest_sha256": labelset_sha,
            "labelset_validation_receipt_sha256": validation_sha,
            "label_content_sha256": labelset["label_content_sha256"],
            "query_region_ids": expected_queries,
            "review_pair_receipt_sha256_by_query": expected_pair_hashes,
        }
    )
    if value["labelset_purpose_binding_sha256"] != expected_purpose_binding:
        raise QualifiedLabelReleaseError(
            "Labelset/query/review lineage is not immutably bound to purpose."
        )
    for field in (
        "qa_receipt_sha256",
        "agreement_evidence_sha256",
        "raster_lineage_sha256",
        "consensus_receipt_sha256",
        "adjudication_import_receipt_sha256",
    ):
        _sha256(value[field], field)
    if (
        validation["agreement_evidence_sha256"] != value["agreement_evidence_sha256"]
        or validation["raster_lineage_sha256"] != value["raster_lineage_sha256"]
    ):
        raise QualifiedLabelReleaseError(
            "Labelset validation evidence lineage differs from the release."
        )
    for pair in pairs:
        if (
            pair["agreement_evidence_sha256"] != value["agreement_evidence_sha256"]
            or pair["consensus_receipt_sha256"] != value["consensus_receipt_sha256"]
        ):
            raise QualifiedLabelReleaseError(
                "Qualified release pair lineage is inconsistent."
            )
        adjudication = pair["adjudication"]
        if (
            adjudication is not None
            and adjudication["adjudication_import_receipt_sha256"]
            != value["adjudication_import_receipt_sha256"]
        ):
            raise QualifiedLabelReleaseError(
                "Qualified release adjudication lineage is inconsistent."
            )
    counts = _class_counts(value["class_counts"])
    if value["class_counts"] != counts:
        raise QualifiedLabelReleaseError(
            "Qualified label-release class counts are not canonical."
        )
    binary_count = sum(counts[str(code)] for code in BINARY_ELIGIBLE_CODES)
    excluded_count = sum(counts[str(code)] for code in BINARY_EXCLUDED_CODES)
    if (
        value["binary_eligible_codes"] != list(BINARY_ELIGIBLE_CODES)
        or value["binary_excluded_codes"] != list(BINARY_EXCLUDED_CODES)
        or value["binary_eligible_cell_count"] != binary_count
        or value["binary_excluded_cell_count"] != excluded_count
        or value["unknown_cells_preserved"] is not True
    ):
        raise QualifiedLabelReleaseError(
            "Qualified release lost protected unknown-label semantics."
        )
    if purpose == "flood_model_training_labels":
        if counts["1"] == 0 or counts["0"] + counts["2"] == 0:
            raise QualifiedLabelReleaseError(
                "Training release requires positive and explicit negative labels."
            )
        expected_training, expected_evaluation = True, False
    else:
        expected_training, expected_evaluation = False, True
    if (
        value["eligible_for_query_model_training"] is not expected_training
        or value["eligible_for_flood_model_training"] is not expected_training
        or value["eligible_for_model_evaluation"] is not expected_evaluation
        or value["processing_allowed"] is not True
    ):
        raise QualifiedLabelReleaseError(
            "Qualified label-release purpose eligibility is inconsistent."
        )
    created = _timestamp(value["created_at_utc"], "created_at_utc")
    latest_lineage_time = max(
        _timestamp(
            authorization["created_at_utc"],
            "formal authorization created_at_utc",
        ),
        _timestamp(reference["generated_at"], "qualified reference generated_at"),
        _timestamp(labelset.get("created_at_utc"), "labelset created_at_utc"),
        _timestamp(
            validation.get("validated_at_utc"),
            "labelset validation validated_at_utc",
        ),
        *(_latest_pair_time(pair) for pair in pairs),
    )
    if created < latest_lineage_time:
        raise QualifiedLabelReleaseError(
            "Qualified label release predates review, adjudication, labelset, "
            "reference, or validation evidence."
        )
    _require_false_safety(value, "qualified label release")
    _assumptions(value["assumptions"])
    _reject_fixture_authority(
        _dataset_mode(value["dataset_mode"]),
        evidence_kind=str(authorization["authority_evidence_kind"]),
        artifacts=(authorization, value),
    )
    return value


def _validate_strict_human_roles(
    package: Mapping[str, object],
) -> dict[str, dict[str, object]]:
    if package.get("artifact_schema") != HUMAN_ROLE_PACKAGE_SCHEMA:
        raise QualifiedLabelReleaseError("Human-role package schema is unsupported.")
    if (
        package.get("formal_review_authorized") is not True
        or package.get("package_status") != "formal_review_gate_open_independent_a_b"
        or package.get("genuinely_blinded_double_review") is not True
        or package.get("reference_authority_adjudicator_dual_role_allowed") is not False
    ):
        raise QualifiedLabelReleaseError(
            "Strict review requires an independent A/B gate and separate RA/C."
        )
    _require_false_fields(
        package,
        (
            "eligible_for_model_training",
            "eligible_for_query_model_training",
            "eligible_for_decision_layer",
            "eligible_for_fpps",
            "eligible_for_warning",
        ),
        "human-role package",
    )
    raw_appointments = package.get("appointments")
    if not isinstance(raw_appointments, Sequence) or isinstance(
        raw_appointments, (str, bytes, bytearray)
    ):
        raise QualifiedLabelReleaseError(
            "Human-role package appointments must be an array."
        )
    roles: dict[str, dict[str, object]] = {}
    for raw in raw_appointments:
        if not isinstance(raw, Mapping):
            raise QualifiedLabelReleaseError(
                "Human-role package appointment is malformed."
            )
        category = _text(raw.get("role_category"), "role_category")
        if category not in ROLE_CATEGORIES or category in roles:
            raise QualifiedLabelReleaseError(
                "Human-role package roles are duplicated or unknown."
            )
        role = {
            "role_id": _safe_id(raw.get("role_id"), f"{category} role_id"),
            "person_id": _safe_id(raw.get("person_id"), f"{category} person_id"),
            "review_lane": _text(raw.get("review_lane"), f"{category} review_lane"),
            "project_operator": _strict_bool(
                raw.get("project_operator"), f"{category} project_operator"
            ),
            "prior_prohibited_evidence_exposure": _strict_bool(
                raw.get("prior_prohibited_evidence_exposure"),
                f"{category} prior_prohibited_evidence_exposure",
            ),
            "appointment_status": _text(
                raw.get("appointment_status"), f"{category} appointment_status"
            ),
            "qualification_evidence_id": _text(
                raw.get("qualification_evidence_id"),
                f"{category} qualification_evidence_id",
            ),
        }
        if _ROLE_ID_RE_BY_CATEGORY[category].fullmatch(str(role["role_id"])) is None:
            raise QualifiedLabelReleaseError(
                f"{category} role_id does not match its governed role namespace."
            )
        if role["appointment_status"] != ("accepted_with_attributable_local_evidence"):
            raise QualifiedLabelReleaseError(
                f"{category} appointment is not accepted with attributable evidence."
            )
        roles[category] = role
    if set(roles) != set(ROLE_CATEGORIES):
        raise QualifiedLabelReleaseError(
            "Strict review requires exactly RA, A, B, and C."
        )
    person_ids = [str(roles[category]["person_id"]) for category in ROLE_CATEGORIES]
    if len(set(person_ids)) != 4:
        raise QualifiedLabelReleaseError(
            "Strict review requires four distinct people for RA, A, B, and C."
        )
    for category in REVIEWER_CATEGORIES:
        reviewer = roles[category]
        if (
            reviewer["review_lane"] != "independent_blinded"
            or reviewer["project_operator"] is not False
            or reviewer["prior_prohibited_evidence_exposure"] is not False
        ):
            raise QualifiedLabelReleaseError(
                f"{category} must be independent, blinded, non-operator, and unexposed."
            )
    for category in ("reference_authority", "adjudicator_c"):
        authority = roles[category]
        if (
            authority["review_lane"] != "authority_role_not_blinded"
            or authority["project_operator"] is not False
            or authority["prior_prohibited_evidence_exposure"] is not False
        ):
            raise QualifiedLabelReleaseError(
                f"{category} must use the separate authority lane."
            )
    return {category: roles[category] for category in ROLE_CATEGORIES}


def _validate_calibration_receipt(
    receipt: Mapping[str, object],
    *,
    roles: Mapping[str, Mapping[str, object]],
    protocol_version: str,
    taxonomy_version: str,
) -> None:
    if receipt.get("artifact_schema") != REVIEWER_CALIBRATION_SCHEMA:
        raise QualifiedLabelReleaseError(
            "Reviewer calibration receipt schema is unsupported."
        )
    if (
        receipt.get("calibration_passed") is not True
        or receipt.get("dataset_role") != "reviewer_calibration"
        or receipt.get("protocol_version") != protocol_version
        or receipt.get("taxonomy_version") != taxonomy_version
    ):
        raise QualifiedLabelReleaseError(
            "Reviewer calibration does not pass the exact protocol and taxonomy."
        )
    expected_reviewers = {
        str(roles[category]["role_id"]) for category in REVIEWER_CATEGORIES
    }
    reviewers = _unique_text_array(
        receipt.get("reviewer_ids"), "calibration reviewer_ids", minimum=2
    )
    if set(reviewers) != expected_reviewers or len(reviewers) != 2:
        raise QualifiedLabelReleaseError(
            "Reviewer calibration does not cover exactly appointed A and B."
        )
    _require_false_fields(
        receipt,
        (
            "eligible_for_query_model_training",
            "eligible_for_decision_layer",
            "eligible_for_fpps",
            "eligible_for_warning",
        ),
        "reviewer calibration receipt",
    )
    _sha256(
        receipt.get("query_manifest_sha256"),
        "calibration query manifest SHA-256",
    )
    _sha256(
        receipt.get("calibration_reference_manifest_sha256"),
        "calibration reference manifest SHA-256",
    )


def _validate_annotation_pair(
    annotation_a: Mapping[str, object],
    annotation_b: Mapping[str, object],
    *,
    authorization: Mapping[str, object],
    bundle_sha_by_category: Mapping[str, str],
) -> dict[str, object]:
    roles = authorization["roles"]
    if not isinstance(roles, Mapping):
        raise QualifiedLabelReleaseError(
            "Formal-review authorization roles are malformed."
        )
    annotations = {
        "reviewer_a": annotation_a,
        "reviewer_b": annotation_b,
    }
    not_before = _timestamp(
        authorization["formal_review_not_before_utc"],
        "formal review not-before",
    )
    authorization_created = _timestamp(
        authorization["created_at_utc"], "formal authorization created_at_utc"
    )
    expires = _timestamp(authorization["expires_at_utc"], "formal review expiry")
    locks: dict[str, datetime] = {}
    common_fields = (
        "event_id",
        "tile_id",
        "query_region_id",
        "grid_contract_sha256",
        "source_registry_sha256",
        "context_manifest_sha256",
        "protocol_version",
    )
    for category, annotation in annotations.items():
        required = {
            "annotation_id",
            "event_id",
            "tile_id",
            "query_region_id",
            "reviewer_id",
            "reviewer_revision",
            "primary_class",
            "confidence",
            "review_complete",
            "reviewed_extent",
            "review_started_at",
            "review_finished_at",
            "protocol_version",
            "model_predictions_visible",
            "other_reviewer_annotations_visible",
            "created_at_utc",
            "locked_at_utc",
            "review_stage",
            "bundle_manifest_sha256",
            "context_manifest_sha256",
            "grid_contract_sha256",
            "source_registry_sha256",
        }
        missing = sorted(required - set(annotation))
        if missing:
            raise QualifiedLabelReleaseError(
                f"{category} annotation lacks explicit field(s): " + ", ".join(missing)
            )
        expected_id = roles[category]["role_id"]
        _safe_id(annotation["annotation_id"], f"{category} annotation_id")
        _safe_id(annotation["event_id"], f"{category} event_id")
        _safe_id(annotation["tile_id"], f"{category} tile_id")
        _safe_id(annotation["query_region_id"], f"{category} query_region_id")
        if annotation["reviewer_id"] != expected_id:
            raise QualifiedLabelReleaseError(
                f"{category} annotation uses an unappointed reviewer."
            )
        expected_stage = "primary" if category == "reviewer_a" else "secondary"
        if annotation["review_stage"] != expected_stage:
            raise QualifiedLabelReleaseError(
                f"{category} annotation has the wrong review stage."
            )
        if (
            annotation["model_predictions_visible"] is not False
            or annotation["other_reviewer_annotations_visible"] is not False
        ):
            raise QualifiedLabelReleaseError(
                f"{category} annotation reports a blinding breach."
            )
        if annotation["review_complete"] is not True:
            raise QualifiedLabelReleaseError(f"{category} annotation is not complete.")
        revision = annotation["reviewer_revision"]
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise QualifiedLabelReleaseError(
                f"{category} reviewer_revision must be a positive integer."
            )
        if annotation["confidence"] not in {"high", "medium", "low"}:
            raise QualifiedLabelReleaseError(
                f"{category} confidence is outside the review contract."
            )
        label = _label_code(annotation["primary_class"], f"{category} primary_class")
        if label == 255:
            raise QualifiedLabelReleaseError(
                f"{category} complete annotation cannot remain unreviewed."
            )
        _text(annotation["reviewed_extent"], f"{category} reviewed_extent")
        started = _timestamp(
            annotation["review_started_at"], f"{category} review_started_at"
        )
        finished = _timestamp(
            annotation["review_finished_at"], f"{category} review_finished_at"
        )
        locked = _timestamp(annotation["locked_at_utc"], f"{category} locked_at_utc")
        created = _timestamp(annotation["created_at_utc"], f"{category} created_at_utc")
        if (
            started < max(not_before, authorization_created)
            or not started <= finished <= created <= locked
            or locked > expires
        ):
            raise QualifiedLabelReleaseError(
                f"{category} review chronology is outside its authorization."
            )
        locks[category] = locked
        expected_bundle = _sha256(
            bundle_sha_by_category[category], f"{category} bundle SHA-256"
        )
        if annotation["bundle_manifest_sha256"] != expected_bundle:
            raise QualifiedLabelReleaseError(
                f"{category} annotation is bound to a different bundle."
            )
        for field in (
            "grid_contract_sha256",
            "source_registry_sha256",
            "context_manifest_sha256",
        ):
            _sha256(annotation[field], f"{category} {field}")
    for field in common_fields:
        if annotation_a[field] != annotation_b[field]:
            raise QualifiedLabelReleaseError(
                f"Reviewer annotations differ on common {field}."
            )
    if annotation_a["event_id"] != authorization["event_id"]:
        raise QualifiedLabelReleaseError(
            "Reviewer annotations belong to a different event."
        )
    if annotation_a["protocol_version"] != authorization["protocol_version"]:
        raise QualifiedLabelReleaseError(
            "Reviewer annotations use a protocol outside their authorization."
        )
    if annotation_a["annotation_id"] == annotation_b["annotation_id"]:
        raise QualifiedLabelReleaseError("Reviewer annotations must have distinct IDs.")
    return {
        "grid_contract_sha256": annotation_a["grid_contract_sha256"],
        "source_registry_sha256": annotation_a["source_registry_sha256"],
        "context_manifest_sha256": annotation_a["context_manifest_sha256"],
        "locked_at_by_reviewer": locks,
    }


def _pair_disagreement_reasons(
    annotation_a: Mapping[str, object],
    annotation_b: Mapping[str, object],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if annotation_a["primary_class"] != annotation_b["primary_class"]:
        reasons.append("class_disagreement")
    if _normalized_geometry(annotation_a.get("geometry")) != _normalized_geometry(
        annotation_b.get("geometry")
    ):
        reasons.append("geometry_disagreement")
    if _normalized_geometry(
        annotation_a.get("reviewed_extent")
    ) != _normalized_geometry(annotation_b.get("reviewed_extent")):
        reasons.append("reviewed_extent_disagreement")
    if annotation_a.get("confidence") == "low":
        reasons.append("low_confidence_a")
    if annotation_b.get("confidence") == "low":
        reasons.append("low_confidence_b")
    if _label_code(annotation_a["primary_class"], "reviewer A class") == 3:
        reasons.append("uncertain_a")
    if _label_code(annotation_b["primary_class"], "reviewer B class") == 3:
        reasons.append("uncertain_b")
    if _label_code(annotation_a["primary_class"], "reviewer A class") == 4:
        reasons.append("unobservable_a")
    if _label_code(annotation_b["primary_class"], "reviewer B class") == 4:
        reasons.append("unobservable_b")
    return tuple(reasons)


def _validate_adjudication(
    adjudication: Mapping[str, object] | None,
    *,
    annotation_a: Mapping[str, object],
    annotation_b: Mapping[str, object],
    adjudicator_id: object,
    reveal_at_utc: datetime,
    disagreement_reasons: Sequence[str],
    consensus_receipt_sha256: str,
) -> dict[str, object] | None:
    if not disagreement_reasons:
        if adjudication is not None:
            raise QualifiedLabelReleaseError(
                "Directly agreeing review pair must not invent adjudication."
            )
        return None
    if adjudication is None:
        raise QualifiedLabelReleaseError(
            "Every disagreement or ambiguity requires adjudication."
        )
    wrapper = _mapping_copy(adjudication, "adjudication binding")
    _exact_fields(
        wrapper,
        {
            "queue_item",
            "record",
            "adjudication_bundle_sha256",
            "adjudication_import_receipt_sha256",
            "consensus_receipt_sha256",
            "model_predictions_visible",
        },
        "adjudication binding",
    )
    if wrapper["model_predictions_visible"] is not False:
        raise QualifiedLabelReleaseError(
            "Adjudicator cannot receive model predictions in this milestone."
        )
    queue = _mapping_copy(wrapper["queue_item"], "adjudication queue item")
    record = _mapping_copy(wrapper["record"], "adjudication record")
    annotation_sha = {
        "a": canonical_sha256(annotation_a),
        "b": canonical_sha256(annotation_b),
    }
    expected_queue = {
        "event_id": annotation_a["event_id"],
        "tile_id": annotation_a["tile_id"],
        "query_region_id": annotation_a["query_region_id"],
        "reviewer_a_annotation_id": annotation_a["annotation_id"],
        "reviewer_b_annotation_id": annotation_b["annotation_id"],
        "reviewer_a_sha256": annotation_sha["a"],
        "reviewer_b_sha256": annotation_sha["b"],
    }
    for field, expected in expected_queue.items():
        if queue.get(field) != expected:
            raise QualifiedLabelReleaseError(
                f"Adjudication queue {field} differs from the locked pair."
            )
    if queue.get("status") != "open":
        raise QualifiedLabelReleaseError(
            "Bound adjudication queue item must be the immutable open request."
        )
    queue_created = _timestamp(
        queue.get("created_at_utc"), "adjudication queue created_at_utc"
    )
    if queue_created < reveal_at_utc:
        raise QualifiedLabelReleaseError(
            "Adjudication queue cannot predate locked-pair reveal."
        )
    queue_reasons = queue.get("reason_codes")
    if isinstance(queue_reasons, str):
        normalized_reasons = [
            item.strip() for item in queue_reasons.split(";") if item.strip()
        ]
    elif isinstance(queue_reasons, Sequence) and not isinstance(
        queue_reasons, (str, bytes, bytearray)
    ):
        normalized_reasons = [str(item).strip() for item in queue_reasons]
    else:
        raise QualifiedLabelReleaseError(
            "Adjudication queue reason codes are malformed."
        )
    if set(normalized_reasons) != set(disagreement_reasons):
        raise QualifiedLabelReleaseError(
            "Adjudication queue does not exactly cover pair disagreements."
        )
    expected_record = {
        "queue_id": queue.get("queue_id"),
        **expected_queue,
        "adjudicator_id": adjudicator_id,
    }
    for field, expected in expected_record.items():
        if record.get(field) != expected:
            raise QualifiedLabelReleaseError(
                f"Adjudication record {field} differs from the queue or roles."
            )
    resolved = _timestamp(record.get("resolved_at_utc"), "adjudication resolved_at_utc")
    locked = _timestamp(record.get("locked_at_utc"), "adjudication locked_at_utc")
    if resolved < reveal_at_utc or locked < resolved:
        raise QualifiedLabelReleaseError(
            "Adjudication chronology predates pair reveal or lock."
        )
    outcome = _text(record.get("outcome"), "adjudication outcome")
    if outcome not in {
        "accept_a",
        "accept_b",
        "redraw",
        "uncertain",
        "unobservable",
        "reject",
    }:
        raise QualifiedLabelReleaseError("Unknown adjudication outcome.")
    if record.get("protocol_version") != annotation_a["protocol_version"]:
        raise QualifiedLabelReleaseError(
            "Adjudication protocol differs from the locked reviewer pair."
        )
    final_class = record.get("final_primary_class")
    final_geometry = _normalized_geometry(record.get("final_geometry"))
    if outcome == "accept_a":
        expected_class = _label_code(
            annotation_a["primary_class"], "reviewer A primary_class"
        )
        if _label_code(
            final_class, "adjudication final_primary_class"
        ) != expected_class or final_geometry != _normalized_geometry(
            annotation_a.get("geometry")
        ):
            raise QualifiedLabelReleaseError(
                "accept_a adjudication does not preserve reviewer A's decision."
            )
    elif outcome == "accept_b":
        expected_class = _label_code(
            annotation_b["primary_class"], "reviewer B primary_class"
        )
        if _label_code(
            final_class, "adjudication final_primary_class"
        ) != expected_class or final_geometry != _normalized_geometry(
            annotation_b.get("geometry")
        ):
            raise QualifiedLabelReleaseError(
                "accept_b adjudication does not preserve reviewer B's decision."
            )
    elif outcome == "uncertain":
        if (
            _label_code(final_class, "adjudication final_primary_class") != 3
            or final_geometry
        ):
            raise QualifiedLabelReleaseError(
                "uncertain adjudication must resolve to code 3 without geometry."
            )
    elif outcome == "unobservable":
        if (
            _label_code(final_class, "adjudication final_primary_class") != 4
            or final_geometry
        ):
            raise QualifiedLabelReleaseError(
                "unobservable adjudication must resolve to code 4 without geometry."
            )
    elif outcome == "reject":
        if final_class is not None or final_geometry:
            raise QualifiedLabelReleaseError(
                "reject adjudication cannot retain a class or geometry."
            )
    elif (
        _label_code(final_class, "adjudication final_primary_class") == 255
        or not final_geometry
    ):
        raise QualifiedLabelReleaseError(
            "redraw adjudication requires an explicit reviewed class and geometry."
        )
    if wrapper["consensus_receipt_sha256"] != consensus_receipt_sha256:
        raise QualifiedLabelReleaseError(
            "Adjudication and pair consensus receipts differ."
        )
    return {
        "queue_id": _text(queue.get("queue_id"), "queue_id"),
        "queue_item_sha256": canonical_sha256(queue),
        "adjudication_id": _text(record.get("adjudication_id"), "adjudication_id"),
        "adjudication_record_sha256": canonical_sha256(record),
        "adjudicator_id": str(adjudicator_id),
        "outcome": outcome,
        "adjudication_bundle_sha256": _sha256(
            wrapper["adjudication_bundle_sha256"],
            "adjudication bundle SHA-256",
        ),
        "adjudication_import_receipt_sha256": _sha256(
            wrapper["adjudication_import_receipt_sha256"],
            "adjudication import receipt SHA-256",
        ),
        "consensus_receipt_sha256": _sha256(
            wrapper["consensus_receipt_sha256"],
            "adjudication consensus receipt SHA-256",
        ),
        "model_predictions_visible": False,
        "resolved_at_utc": _iso_utc(resolved),
        "locked_at_utc": _iso_utc(locked),
    }


def _validate_labelset_validation(
    labelset: Mapping[str, object],
    validation: Mapping[str, object],
    *,
    authorization: Mapping[str, object],
) -> None:
    if validation.get("artifact_schema") != LABELSET_VALIDATION_SCHEMA:
        raise QualifiedLabelReleaseError(
            "Labelset validation receipt schema is unsupported."
        )
    if validation.get("labelset_id") != labelset.get("labelset_id") or validation.get(
        "labelset_manifest_sha256"
    ) != labelset.get("manifest_sha256"):
        raise QualifiedLabelReleaseError(
            "Labelset validation receipt binds a different manifest."
        )
    if (
        validation.get("qa_ready") is not True
        or validation.get("open_adjudication_count") != 0
        or validation.get("eligible_for_query_model_training") is not True
    ):
        raise QualifiedLabelReleaseError(
            "Labelset validation receipt is not release-ready."
        )
    _timestamp(labelset.get("created_at_utc"), "labelset created_at_utc")
    _timestamp(
        validation.get("validated_at_utc"),
        "labelset validation validated_at_utc",
    )
    if validation.get("reviewer_calibration_receipt_sha256") != authorization.get(
        "reviewer_calibration_receipt_sha256"
    ):
        raise QualifiedLabelReleaseError(
            "Labelset validation is bound to a different reviewer calibration."
        )
    _sha256(
        validation.get("agreement_evidence_sha256"),
        "labelset validation agreement evidence SHA-256",
    )
    _sha256(
        validation.get("raster_lineage_sha256"),
        "labelset validation raster lineage SHA-256",
    )
    _require_false_fields(
        validation,
        (
            "eligible_for_decision_layer",
            "eligible_for_fpps",
            "eligible_for_warning",
        ),
        "labelset validation receipt",
    )


def _validate_pair_envelope(
    pair: Mapping[str, object],
    *,
    authorization: Mapping[str, object],
) -> dict[str, object]:
    value = _mapping_copy(pair, "review-pair receipt")
    _exact_fields(
        value,
        {
            "artifact_schema",
            "pair_id",
            "dataset_mode",
            "synthetic_fixture_only",
            "release_purpose",
            "event_id",
            "study_area_id",
            "tile_id",
            "query_region_id",
            "formal_review_authorization_sha256",
            "human_role_package_sha256",
            "reviewer_ids",
            "reviewer_annotation_ids",
            "reviewer_annotation_sha256",
            "reviewer_bundle_sha256",
            "reviewer_evidence_set_sha256",
            "review_evidence_set_sha256",
            "grid_contract_sha256",
            "source_registry_sha256",
            "context_manifest_sha256",
            "locked_at_by_reviewer",
            "reveal_at_utc",
            "model_predictions_visible",
            "other_reviewer_annotations_visible",
            "disagreement_reasons",
            "agreement_evidence_sha256",
            "consensus_receipt_sha256",
            "adjudication",
            "pair_outcome",
            "eligible_for_label_release",
            "processing_allowed",
            *DOWNSTREAM_SAFETY_FIELDS,
            "assumptions",
            "receipt_sha256",
        },
        "review-pair envelope",
    )
    if value.get("artifact_schema") != REVIEW_PAIR_EVIDENCE_SCHEMA:
        raise QualifiedLabelReleaseError(
            "Review-pair envelope has an unsupported schema."
        )
    _verify_self_hash(value, "receipt_sha256", "review-pair receipt")
    _safe_id(value["pair_id"], "pair_id")
    _safe_id(value["tile_id"], "tile_id")
    _safe_id(value["query_region_id"], "query_region_id")
    if (
        value.get("formal_review_authorization_sha256")
        != authorization.get("receipt_sha256")
        or value.get("human_role_package_sha256")
        != authorization.get("human_role_package_sha256")
        or value.get("dataset_mode") != authorization.get("dataset_mode")
        or value.get("synthetic_fixture_only")
        is not authorization.get("synthetic_fixture_only")
        or value.get("release_purpose") != authorization.get("release_purpose")
        or value.get("event_id") != authorization.get("event_id")
        or value.get("study_area_id") != authorization.get("study_area_id")
    ):
        raise QualifiedLabelReleaseError(
            "Review-pair envelope authorization lineage differs."
        )
    if value["reviewer_ids"] != authorization["reviewer_ids"]:
        raise QualifiedLabelReleaseError(
            "Review-pair envelope reviewer identities differ from authorization."
        )
    annotation_ids = value["reviewer_annotation_ids"]
    if not isinstance(annotation_ids, Mapping) or set(annotation_ids) != {
        "reviewer_a",
        "reviewer_b",
    }:
        raise QualifiedLabelReleaseError(
            "Review-pair annotation IDs must cover exactly A and B."
        )
    normalized_annotation_ids = {
        category: _safe_id(identifier, f"{category} annotation_id")
        for category, identifier in annotation_ids.items()
    }
    if len(set(normalized_annotation_ids.values())) != 2:
        raise QualifiedLabelReleaseError(
            "Review-pair annotations must have distinct IDs."
        )
    _sha_mapping(
        value["reviewer_annotation_sha256"],
        expected_keys={"reviewer_a", "reviewer_b"},
        label="reviewer annotation hashes",
    )
    _sha_mapping(
        value["reviewer_bundle_sha256"],
        expected_keys={"reviewer_a", "reviewer_b"},
        label="reviewer bundle hashes",
    )
    evidence_hashes = _sha_mapping(
        value["reviewer_evidence_set_sha256"],
        expected_keys={"reviewer_a", "reviewer_b"},
        label="reviewer evidence-set hashes",
    )
    common_evidence_sha = _sha256(
        value["review_evidence_set_sha256"], "review evidence-set SHA-256"
    )
    if (
        evidence_hashes["reviewer_a"] != evidence_hashes["reviewer_b"]
        or evidence_hashes["reviewer_a"] != common_evidence_sha
    ):
        raise QualifiedLabelReleaseError(
            "Review-pair envelope does not prove an identical evidence set."
        )
    for field in (
        "grid_contract_sha256",
        "source_registry_sha256",
        "context_manifest_sha256",
        "agreement_evidence_sha256",
        "consensus_receipt_sha256",
    ):
        _sha256(value[field], field)
    locks = value["locked_at_by_reviewer"]
    if not isinstance(locks, Mapping) or set(locks) != {
        "reviewer_a",
        "reviewer_b",
    }:
        raise QualifiedLabelReleaseError(
            "Review-pair lock mapping must cover exactly A and B."
        )
    lock_times = [
        _timestamp(locks[category], f"{category} locked_at_utc")
        for category in REVIEWER_CATEGORIES
    ]
    reveal = _timestamp(value["reveal_at_utc"], "reveal_at_utc")
    if reveal < max(lock_times) or reveal > _timestamp(
        authorization["expires_at_utc"], "formal review expiry"
    ):
        raise QualifiedLabelReleaseError(
            "Review-pair envelope reveal is outside its authorized lock window."
        )
    if (
        value.get("model_predictions_visible") is not False
        or value.get("other_reviewer_annotations_visible") is not False
    ):
        raise QualifiedLabelReleaseError(
            "Review-pair envelope contains a blinding breach."
        )
    disagreement_reasons = _unique_text_array(
        value["disagreement_reasons"], "disagreement_reasons"
    )
    adjudication = value["adjudication"]
    if disagreement_reasons and not isinstance(adjudication, Mapping):
        raise QualifiedLabelReleaseError(
            "Review-pair disagreement lacks adjudication evidence."
        )
    if not disagreement_reasons and adjudication is not None:
        raise QualifiedLabelReleaseError(
            "Review-pair agreement cannot invent adjudication evidence."
        )
    if adjudication is None:
        expected_outcome = "paired_agreement_locked"
    else:
        _exact_fields(
            adjudication,
            {
                "queue_id",
                "queue_item_sha256",
                "adjudication_id",
                "adjudication_record_sha256",
                "adjudicator_id",
                "outcome",
                "adjudication_bundle_sha256",
                "adjudication_import_receipt_sha256",
                "consensus_receipt_sha256",
                "model_predictions_visible",
                "resolved_at_utc",
                "locked_at_utc",
            },
            "review-pair adjudication summary",
        )
        if (
            adjudication["adjudicator_id"]
            != authorization["roles"]["adjudicator_c"]["role_id"]
            or adjudication["model_predictions_visible"] is not False
            or adjudication["consensus_receipt_sha256"]
            != value["consensus_receipt_sha256"]
        ):
            raise QualifiedLabelReleaseError(
                "Review-pair adjudication summary violates role or lineage binding."
            )
        _safe_id(adjudication["queue_id"], "adjudication queue_id")
        _safe_id(adjudication["adjudication_id"], "adjudication_id")
        if adjudication["outcome"] not in {
            "accept_a",
            "accept_b",
            "redraw",
            "uncertain",
            "unobservable",
            "reject",
        }:
            raise QualifiedLabelReleaseError(
                "Review-pair adjudication summary has an unknown outcome."
            )
        for field in (
            "queue_item_sha256",
            "adjudication_record_sha256",
            "adjudication_bundle_sha256",
            "adjudication_import_receipt_sha256",
            "consensus_receipt_sha256",
        ):
            _sha256(adjudication[field], f"adjudication {field}")
        resolved = _timestamp(
            adjudication["resolved_at_utc"], "adjudication resolved_at_utc"
        )
        locked = _timestamp(adjudication["locked_at_utc"], "adjudication locked_at_utc")
        if resolved < reveal or locked < resolved:
            raise QualifiedLabelReleaseError(
                "Review-pair adjudication summary chronology is invalid."
            )
        expected_outcome = (
            "excluded_rejected"
            if adjudication["outcome"] == "reject"
            else "adjudicated_locked"
        )
    if value["pair_outcome"] != expected_outcome:
        raise QualifiedLabelReleaseError(
            "Review-pair envelope outcome is inconsistent."
        )
    eligible = expected_outcome != "excluded_rejected"
    if (
        value["eligible_for_label_release"] is not eligible
        or value["processing_allowed"] is not eligible
    ):
        raise QualifiedLabelReleaseError(
            "Review-pair envelope eligibility is inconsistent."
        )
    _require_false_safety(value, "review-pair envelope")
    _assumptions(value["assumptions"])
    return value


def _reject_fixture_authority(
    mode: str,
    *,
    evidence_kind: str,
    artifacts: Sequence[Mapping[str, object]],
) -> None:
    if mode == "fixture_demo":
        if evidence_kind != "synthetic_fixture_only":
            raise QualifiedLabelReleaseError(
                "Fixture mode must disclose synthetic fixture authority."
            )
        return
    if evidence_kind != "production_attributable_evidence":
        raise QualifiedLabelReleaseError(
            "Candidate/official mode rejects synthetic fixture authority."
        )
    for artifact in artifacts:
        if _contains_fixture_marker(artifact):
            raise QualifiedLabelReleaseError(
                "Candidate/official mode rejects synthetic authority artifacts."
            )
        if artifact.get("confers_authority") is False:
            raise QualifiedLabelReleaseError(
                "Candidate/official mode rejects non-authoritative fixture evidence."
            )


def _contains_fixture_marker(value: object) -> bool:
    if isinstance(value, Mapping):
        if (
            value.get("dataset_mode") == "fixture_demo"
            or value.get("synthetic_fixture_only") is True
            or value.get("authority_evidence_kind") == "synthetic_fixture_only"
        ):
            return True
        return any(_contains_fixture_marker(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_fixture_marker(item) for item in value)
    return value == "synthetic_fixture_only"


def _reject_private_paths(value: object, *, field: str = "artifact") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_private_paths(item, field=f"{field}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _reject_private_paths(item, field=f"{field}[{index}]")
        return
    if isinstance(value, str) and _PRIVATE_PATH_RE.search(value):
        raise QualifiedLabelReleaseError(f"{field} contains a private absolute path.")


def _false_safety_fields() -> dict[str, bool]:
    return {field: False for field in DOWNSTREAM_SAFETY_FIELDS}


def _require_false_safety(value: Mapping[str, object], label: str) -> None:
    _require_false_fields(value, DOWNSTREAM_SAFETY_FIELDS, label)


def _require_false_fields(
    value: Mapping[str, object],
    fields: Sequence[str],
    label: str,
) -> None:
    unsafe = [field for field in fields if value.get(field) is not False]
    if unsafe:
        raise QualifiedLabelReleaseError(
            f"{label} safety field(s) must be false: " + ", ".join(unsafe)
        )


def _verify_self_hash(value: Mapping[str, object], field: str, label: str) -> str:
    digest = _sha256(value.get(field), f"{label} {field}")
    unsigned = dict(value)
    unsigned.pop(field, None)
    if canonical_sha256(unsigned) != digest:
        raise QualifiedLabelReleaseError(
            f"{label} {field} does not match canonical content."
        )
    return digest


def _load_human_role_package(
    source: Mapping[str, object] | str | Path,
    *,
    dataset_mode: str,
) -> dict[str, object]:
    if isinstance(source, (str, Path)):
        try:
            package = validate_human_role_package(source)
        except (HumanRolePackageError, OSError) as exc:
            raise QualifiedLabelReleaseError(
                f"Human-role package failed its canonical validator: {exc}"
            ) from exc
        return _mapping_copy(package, "human role package")
    if dataset_mode != "fixture_demo":
        raise QualifiedLabelReleaseError(
            "Candidate/official review requires a frozen human-role package "
            "directory validated with its attributable evidence files."
        )
    return _mapping_copy(source, "fixture human role package")


def _load_reviewer_calibration(
    source: Mapping[str, object] | str | Path,
    *,
    dataset_mode: str,
) -> dict[str, object]:
    if isinstance(source, (str, Path)):
        try:
            receipt = load_reviewer_calibration_receipt(source)
        except (ReviewerCalibrationError, OSError) as exc:
            raise QualifiedLabelReleaseError(
                f"Reviewer calibration failed its canonical validator: {exc}"
            ) from exc
        return _mapping_copy(receipt.to_dict(), "reviewer calibration receipt")
    if dataset_mode != "fixture_demo":
        raise QualifiedLabelReleaseError(
            "Candidate/official review requires a complete calibration-receipt "
            "file validated by the canonical calibration loader."
        )
    return _mapping_copy(source, "fixture reviewer calibration receipt")


def _load_labelset_manifest(
    source: Mapping[str, object] | str | Path,
    *,
    dataset_mode: str,
) -> dict[str, object]:
    if isinstance(source, (str, Path)):
        try:
            manifest = load_labelset_manifest(source)
        except (LabelsetVersionError, OSError) as exc:
            raise QualifiedLabelReleaseError(
                f"Labelset manifest failed its canonical validator: {exc}"
            ) from exc
        return _mapping_copy(manifest.to_dict(), "labelset manifest")
    if dataset_mode != "fixture_demo":
        raise QualifiedLabelReleaseError(
            "Candidate/official release requires a frozen labelset-manifest "
            "file validated by the canonical labelset loader."
        )
    return _mapping_copy(source, "fixture labelset manifest")


def _load_labelset_validation(
    source: Mapping[str, object] | str | Path,
    *,
    dataset_mode: str,
) -> dict[str, object]:
    if isinstance(source, (str, Path)):
        try:
            receipt = load_labelset_validation_receipt(source)
        except (ReviewWorkflowError, OSError) as exc:
            raise QualifiedLabelReleaseError(
                f"Labelset validation failed its canonical validator: {exc}"
            ) from exc
        return _mapping_copy(receipt.to_dict(), "labelset validation receipt")
    if dataset_mode != "fixture_demo":
        raise QualifiedLabelReleaseError(
            "Candidate/official release requires a complete labelset-validation "
            "receipt file validated by the canonical review-workflow loader."
        )
    return _mapping_copy(source, "fixture labelset validation receipt")


def _load_qualified_reference_release(
    source: Mapping[str, object] | str | Path,
) -> dict[str, object]:
    try:
        if isinstance(source, (str, Path)):
            receipt = load_qualified_reference_release(source)
        else:
            receipt = validate_qualified_reference_release(
                _mapping_copy(source, "qualified-reference release")
            )
    except (QualifiedReferenceReleaseError, OSError) as exc:
        raise QualifiedLabelReleaseError(
            f"Qualified-reference release failed its canonical validator: {exc}"
        ) from exc
    return _mapping_copy(receipt, "qualified-reference release")


def _validate_reference_compatibility(
    reference: Mapping[str, object],
    *,
    authorization: Mapping[str, object],
    release_purpose: str,
) -> str:
    if reference.get("event_id") != authorization.get("event_id") or reference.get(
        "study_area_id"
    ) != authorization.get("study_area_id"):
        raise QualifiedLabelReleaseError(
            "Qualified-reference event or study area differs from review authority."
        )
    reference_purpose = release_purpose
    if reference.get("purpose") != reference_purpose:
        raise QualifiedLabelReleaseError(
            "Qualified-reference receipt purpose differs from label-release purpose."
        )
    raw_purposes = reference.get("purpose_authorizations")
    if not isinstance(raw_purposes, Sequence) or isinstance(
        raw_purposes, (str, bytes, bytearray)
    ):
        raise QualifiedLabelReleaseError(
            "Qualified-reference purpose authorizations are malformed."
        )
    if (
        len(raw_purposes) != 1
        or not isinstance(raw_purposes[0], Mapping)
        or raw_purposes[0].get("purpose") != reference_purpose
    ):
        raise QualifiedLabelReleaseError(
            "Qualified-reference release lacks an exact purpose authorization."
        )
    purpose_row = raw_purposes[0]
    evidence_sha = reference.get("evidence_bundle_sha256")
    mode = authorization.get("dataset_mode")
    if mode == "fixture_demo":
        if (
            reference.get("dataset_mode") != "fixture_demo"
            or reference.get("release_status") != SYNTHETIC_REFERENCE_STATUS
            or reference.get("processing_allowed") is not False
            or reference.get("synthetic_fixture_processing_allowed") is not True
            or purpose_row.get("status") != "synthetic_fixture_only"
            or not isinstance(evidence_sha, str)
            or purpose_row.get("evidence_sha256") != evidence_sha
        ):
            raise QualifiedLabelReleaseError(
                "Fixture review requires a canonical synthetic qualified-reference "
                "receipt with purpose-bound fixture evidence."
            )
        return reference_purpose

    expected_development = release_purpose == "flood_model_training_labels"
    expected_evaluation = release_purpose == "model_final_evaluation"
    if (
        reference.get("dataset_mode") != "candidate"
        or reference.get("release_status") != QUALIFIED_REFERENCE_STATUS
        or reference.get("processing_allowed") is not True
        or reference.get("eligible_for_controlled_model_development")
        is not expected_development
        or reference.get("eligible_for_controlled_model_evaluation")
        is not expected_evaluation
        or reference.get("synthetic_fixture_processing_allowed") is not False
        or purpose_row.get("status")
        != "reference_gate_passed_downstream_gates_required"
        or not isinstance(evidence_sha, str)
        or purpose_row.get("evidence_sha256") != evidence_sha
    ):
        raise QualifiedLabelReleaseError(
            "Candidate/official review requires a non-synthetic, qualified, "
            "purpose-bound controlled-development reference release."
        )
    return reference_purpose


def _latest_pair_time(pair: Mapping[str, object]) -> datetime:
    timestamps = [_timestamp(pair.get("reveal_at_utc"), "review-pair reveal_at_utc")]
    raw_locks = pair.get("locked_at_by_reviewer")
    if not isinstance(raw_locks, Mapping):
        raise QualifiedLabelReleaseError("Review-pair lock timestamps are malformed.")
    timestamps.extend(
        _timestamp(value, f"review-pair {reviewer} locked_at_utc")
        for reviewer, value in raw_locks.items()
    )
    adjudication = pair.get("adjudication")
    if adjudication is not None:
        if not isinstance(adjudication, Mapping):
            raise QualifiedLabelReleaseError("Review-pair adjudication is malformed.")
        timestamps.extend(
            (
                _timestamp(
                    adjudication.get("resolved_at_utc"),
                    "adjudication resolved_at_utc",
                ),
                _timestamp(
                    adjudication.get("locked_at_utc"),
                    "adjudication locked_at_utc",
                ),
            )
        )
    return max(timestamps)


def _mapping_copy(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise QualifiedLabelReleaseError(f"{label} must be a JSON object.")
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        copied = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise QualifiedLabelReleaseError(
            f"{label} must contain strict JSON values."
        ) from exc
    if not isinstance(copied, dict):
        raise QualifiedLabelReleaseError(f"{label} must be a JSON object.")
    _reject_private_paths(copied, field=label)
    return copied


def _exact_fields(value: Mapping[str, object], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise QualifiedLabelReleaseError(
            f"{label} fields differ; missing={missing}, unexpected={unexpected}."
        )


def _dataset_mode(value: object) -> str:
    mode = _text(value, "dataset_mode")
    if mode not in DATASET_MODES:
        raise QualifiedLabelReleaseError("Unsupported dataset_mode.")
    return mode


def _authority_kind(value: object, *, mode: str) -> str:
    kind = _text(value, "authority_evidence_kind")
    if kind not in AUTHORITY_EVIDENCE_KINDS:
        raise QualifiedLabelReleaseError("Unsupported authority_evidence_kind.")
    if mode == "fixture_demo" and kind != "synthetic_fixture_only":
        raise QualifiedLabelReleaseError(
            "Fixture mode requires synthetic_fixture_only authority."
        )
    return kind


def _purpose(value: object) -> str:
    purpose = _text(value, "purpose")
    if purpose not in RELEASE_PURPOSES:
        raise QualifiedLabelReleaseError("Unsupported qualified-release purpose.")
    return purpose


def _safe_id(value: object, label: str) -> str:
    text = _text(value, label)
    if _SAFE_ID_RE.fullmatch(text) is None:
        raise QualifiedLabelReleaseError(f"{label} must be a stable safe identifier.")
    return text


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QualifiedLabelReleaseError(f"{label} must be nonblank text.")
    return value.strip()


def _strict_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise QualifiedLabelReleaseError(f"{label} must be a JSON boolean.")
    return value


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise QualifiedLabelReleaseError(f"{label} must be a SHA-256 string.")
    normalized = value.strip().lower()
    if _SHA256_RE.fullmatch(normalized) is None:
        raise QualifiedLabelReleaseError(
            f"{label} must contain 64 lowercase hexadecimal digits."
        )
    return normalized


def _timestamp(value: object, label: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise QualifiedLabelReleaseError(f"{label} must be an ISO-8601 timestamp.")
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise QualifiedLabelReleaseError(
                f"{label} must be an ISO-8601 timestamp."
            ) from exc
    else:
        raise QualifiedLabelReleaseError(f"{label} must be an ISO-8601 timestamp.")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise QualifiedLabelReleaseError(f"{label} must include a UTC offset.")
    return parsed.astimezone(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _unique_text_array(value: object, label: str, *, minimum: int = 0) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise QualifiedLabelReleaseError(f"{label} must be an array.")
    values = [_text(item, label) for item in value]
    if len(values) < minimum:
        raise QualifiedLabelReleaseError(
            f"{label} requires at least {minimum} item(s)."
        )
    if len(values) != len(set(values)):
        raise QualifiedLabelReleaseError(f"{label} contains duplicates.")
    return values


def _assumptions(value: object) -> list[str]:
    assumptions = _unique_text_array(value, "assumptions", minimum=1)
    return assumptions


def _sha_mapping(
    value: object, *, expected_keys: set[str], label: str
) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != expected_keys:
        raise QualifiedLabelReleaseError(
            f"{label} must cover exactly: {', '.join(sorted(expected_keys))}."
        )
    return {
        str(key): _sha256(digest, f"{label}[{key}]") for key, digest in value.items()
    }


def _label_code(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise QualifiedLabelReleaseError(f"{label} must be an integer label.")
    try:
        code = int(value)
    except (TypeError, ValueError) as exc:
        raise QualifiedLabelReleaseError(f"{label} must be an integer label.") from exc
    if isinstance(value, float) and not math.isclose(value, code):
        raise QualifiedLabelReleaseError(f"{label} must be an integer label.")
    if code not in SAFE_LABEL_CODES:
        raise QualifiedLabelReleaseError(
            f"{label} is outside the protected flood-label taxonomy."
        )
    return code


def _class_counts(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise QualifiedLabelReleaseError("class_counts must be an object.")
    normalized = {str(key): count for key, count in value.items()}
    expected = {str(code) for code in SAFE_LABEL_CODES}
    if set(normalized) != expected:
        raise QualifiedLabelReleaseError(
            "class_counts must cover exactly 0, 1, 2, 3, 4, and 255."
        )
    result: dict[str, int] = {}
    for code, count in normalized.items():
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise QualifiedLabelReleaseError(
                f"class_counts[{code}] must be a non-negative integer."
            )
        result[code] = count
    if sum(result.values()) == 0:
        raise QualifiedLabelReleaseError("class_counts must not be empty.")
    return {str(code): result[str(code)] for code in SAFE_LABEL_CODES}


def _normalized_geometry(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise QualifiedLabelReleaseError("Geometry must be WKT text or null.")
    return " ".join(value.split())
