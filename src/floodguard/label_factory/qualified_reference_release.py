"""Build and validate a fail-closed qualified-reference compatibility release.

The release bridges the controlled-experiment acquisition authority into the
label-factory/model-development boundary.  It does not replace the controlled
experiment gate, create provider permission, qualify a reviewer, authorize
FPPS, select an A-E action class, or issue an official warning.

Three states are intentionally supported:

``blocked``
    A deterministic projection of a verified, non-ready
    :class:`~floodguard.controlled_experiment.AcquisitionGateAssessment`.
    Its blockers are preserved verbatim and every processing permission is
    false.

``synthetic_fixture_only``
    A byte- and grid-verified synthetic raster that can exercise integration
    code only.  It never counts as scientific or Thai event evidence.

``qualified_for_controlled_model_development``
    A future state that requires a ready signed acquisition assessment, the
    exact verified acquisition-authority receipt, matching reference bytes,
    product-scoped permissions, an equal-area raster/grid contract, and a
    separate purpose-specific scientific Reference Authority decision with a
    detached signature and runtime-trusted credential. Even this state only
    clears the reference compatibility slice; all downstream experiment,
    promotion, field, and agency gates remain mandatory.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

import floodguard.controlled_experiment as controlled
from floodguard.controlled_experiment import (
    EXTERNAL_PERMISSION_FIELDS,
    AcquisitionGateAssessment,
)


SCHEMA_VERSION = "1.0"
RELEASE_SCHEMA = "floodguard.qualified_reference_release.v1"
REFERENCE_AUTHORITY_DECISION_SCHEMA = (
    "floodguard.reference_authority_scientific_decision.v1"
)

BLOCKED_STATUS = "blocked"
SYNTHETIC_STATUS = "synthetic_fixture_only"
QUALIFIED_STATUS = "qualified_for_controlled_model_development"
RELEASE_STATUSES = frozenset(
    {
        BLOCKED_STATUS,
        SYNTHETIC_STATUS,
        QUALIFIED_STATUS,
    }
)

REFERENCE_AUTHORITY_CLASSES = frozenset(
    {
        "observed_event_extent",
        "expert_interpretation",
        "weak_reference",
        "contextual_evidence",
        "synthetic_fixture",
    }
)
QUALIFIED_AUTHORITY_CLASSES = frozenset(
    {
        "observed_event_extent",
        "expert_interpretation",
    }
)

PURPOSES = (
    "human_reviewer_calibration",
    "human_annotation_reference",
    "flood_model_training_labels",
    "model_probability_calibration",
    "model_final_evaluation",
    "derived_metrics_only",
)
PURPOSE_BLOCKED = "blocked"
PURPOSE_SYNTHETIC = "synthetic_fixture_only"
PURPOSE_QUALIFIED = "reference_gate_passed_downstream_gates_required"

SAFETY_LIMITATIONS = (
    "This release cannot feed the decision layer.",
    "This release cannot feed FPPS.",
    "This release cannot assign an A-E action class.",
    "This release cannot issue an official warning.",
    "This release does not grant agency-operational authority.",
    "A separate controlled-experiment gate remains required.",
)
SYNTHETIC_LIMITATION = (
    "Synthetic fixture only; it is not qualified Thai event evidence and cannot "
    "support scientific or operational claims."
)

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_SAFE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{2,254}")
_COMMIT_RE = re.compile(r"[0-9a-fA-F]{40}")
_EPSG_RE = re.compile(r"EPSG:\d+", re.IGNORECASE)
_PRIVATE_PATH_RE = re.compile(
    r"(?:^|[\s\"'=])(?:[A-Za-z]:[\\/]|file://|"
    r"\\\\[^\\/\s]+[\\/][^\\/\s]+|"
    r"/(?:home|Users|private|tmp|var|opt|mnt|srv|root|Volumes|data|"
    r"workspace|usr|run)(?:[\\/]|$))",
    re.IGNORECASE,
)

_ROOT_KEYS = frozenset(
    {
        "schema_version",
        "artifact_schema",
        "release_id",
        "release_status",
        "dataset_mode",
        "operational_status",
        "study_area_id",
        "study_area_name",
        "event_id",
        "experiment_id",
        "source_timestamp",
        "generated_at",
        "confidence_class",
        "source_name",
        "assumptions",
        "data_version",
        "git_commit",
        "official_warning",
        "evidence_classification",
        "source_permissions",
        "purpose",
        "purpose_authorizations",
        "reference_artifact",
        "analysis_grid",
        "acquisition_lineage",
        "evidence_bundle_sha256",
        "processing_allowed",
        "eligible_for_controlled_model_development",
        "eligible_for_controlled_model_evaluation",
        "synthetic_fixture_processing_allowed",
        "downstream_experiment_gate_required",
        "can_feed_decision_layer",
        "can_feed_fpps",
        "can_assign_action_class",
        "agency_operational_authorized",
        "safety_limitations",
        "blockers",
        "reason_blocked",
        "release_sha256",
    }
)
_CLASSIFICATION_KEYS = frozenset(
    {
        "reference_authority_class",
        "qualification_status",
        "rights_evidence_status",
        "independence_status",
        "purpose_acceptance_status",
        "field_validation_status",
    }
)
_PURPOSE_KEYS = frozenset(
    {
        "purpose",
        "status",
        "authority_basis",
        "evidence_sha256",
    }
)
_ARTIFACT_KEYS = frozenset(
    {
        "product_id",
        "file_name",
        "sha256",
        "media_type",
        "crs",
        "transform",
        "width",
        "height",
        "band_count",
        "dtype",
        "nodata",
        "valid_values",
        "observation_start",
        "observation_end",
        "covers_analysis_grid",
        "reprojection_performed",
    }
)
_GRID_KEYS = frozenset(
    {
        "file_name",
        "sha256",
        "crs",
        "transform",
        "width",
        "height",
        "cell_size",
    }
)
_LINEAGE_KEYS = frozenset(
    {
        "assessment_status",
        "acquisition_manifest_sha256",
        "acquisition_manifest_file_sha256",
        "acquisition_authority_receipt_sha256",
        "authority_signing_key_id",
        "authority_issued_at_utc",
        "authority_expires_at_utc",
        "external_authority_decision_sha256",
        "external_authority_signing_key_id",
        "reference_authorization_sha256",
        "reference_product_id",
        "reference_source_name",
        "reference_source_timestamp",
        "reference_observation_start",
        "reference_observation_end",
        "reference_permissions_sha256",
        "reference_authority_decision_id",
        "reference_authority_decision_sha256",
        "reference_authority_decision_file_sha256",
        "reference_authority_signature_sha256",
        "reference_authority_signature_file_sha256",
        "reference_authority_signing_key_id",
        "reference_authority_public_key_sha256",
        "reference_authority_id",
        "reference_authority_issued_at_utc",
        "reference_authority_expires_at_utc",
        "reference_authority_purpose",
        "reference_authority_class",
        "reference_authority_receipt_sha256",
        "sha256_by_role",
        "assessment_blockers",
    }
)
_REFERENCE_AUTHORITY_DECISION_KEYS = frozenset(
    {
        "schema_version",
        "decision_id",
        "decision_status",
        "event_id",
        "study_area_id",
        "experiment_id",
        "source_name",
        "product_id",
        "artifact_sha256",
        "source_timestamp",
        "observation_start",
        "observation_end",
        "reference_authority_class",
        "purpose",
        "independent_of_model_inputs",
        "scientific_method",
        "known_uncertainty_and_error_categories",
        "issued_at_utc",
        "expires_at_utc",
        "signer",
        "official_warning",
        "can_feed_decision_layer",
        "can_feed_fpps",
        "can_assign_action_class",
    }
)
_REFERENCE_AUTHORITY_SIGNER_KEYS = frozenset(
    {
        "name",
        "organization",
        "title_or_role",
        "authority_basis",
        "identity_evidence_type",
        "identity_evidence_sha256",
        "signing_key_id",
        "public_key_sha256",
    }
)


class QualifiedReferenceReleaseError(ValueError):
    """Raised when a release would be incomplete, misleading, or mutable."""


def build_qualified_reference_release(
    acquisition: AcquisitionGateAssessment | None,
    *,
    release_id: str,
    study_area_id: str,
    event_id: str,
    source_timestamp: str | datetime,
    generated_at: str | datetime,
    source_name: str,
    assumptions: Sequence[str],
    data_version: str,
    git_commit: str,
    purpose: str | None = None,
    release_status: str = BLOCKED_STATUS,
    reference_authority_class: str = "contextual_evidence",
    confidence_class: str = "low",
    experiment_id: str | None = None,
    reference_product_id: str | None = None,
    reference_artifact_path: str | Path | None = None,
    analysis_grid_contract_path: str | Path | None = None,
    acquisition_authority_receipt_path: str | Path | None = None,
    reference_authority_decision_path: str | Path | None = None,
    reference_authority_signature_path: str | Path | None = None,
    reference_authority_public_keys: Mapping[str, bytes] | None = None,
    observation_start: str | datetime | None = None,
    observation_end: str | datetime | None = None,
) -> dict[str, Any]:
    """Build one deterministic compatibility release.

    Qualified output cannot be requested from a non-ready assessment.  A
    blocked projection never accepts artifact/authority inputs, so a caller
    cannot smuggle unverified evidence into a fail-closed record.  Synthetic
    output requires real fixture bytes and a matching equal-area grid contract
    but deliberately has no acquisition or Reference Authority lineage.
    """

    status = _choice(release_status, RELEASE_STATUSES, "release_status")
    if purpose is None:
        if status != BLOCKED_STATUS:
            raise QualifiedReferenceReleaseError(
                "Synthetic and qualified releases require an explicit purpose."
            )
        selected_purpose = "derived_metrics_only"
    else:
        selected_purpose = _choice(purpose, frozenset(PURPOSES), "purpose")
    release_identifier = _identifier(release_id, "release_id")
    area_identifier = _identifier(study_area_id, "study_area_id")
    event_identifier = _identifier(event_id, "event_id")
    version = _identifier(data_version, "data_version")
    commit = _commit(git_commit)
    generated = _timestamp(generated_at, "generated_at")
    source_time = _timestamp(source_timestamp, "source_timestamp")
    if source_time > generated:
        raise QualifiedReferenceReleaseError(
            "source_timestamp cannot be later than generated_at."
        )
    name = _text(source_name, "source_name")
    normalized_assumptions = _assumptions(assumptions)
    authority_class = _choice(
        reference_authority_class,
        REFERENCE_AUTHORITY_CLASSES,
        "reference_authority_class",
    )

    if status == BLOCKED_STATUS:
        if acquisition is None:
            raise QualifiedReferenceReleaseError(
                "A blocked projection requires a verified non-ready acquisition "
                "assessment."
            )
        _require_acquisition(acquisition)
        if acquisition.ready or not acquisition.blockers:
            raise QualifiedReferenceReleaseError(
                "A blocked projection requires a non-ready assessment with blockers."
            )
        _reject_status_only_inputs(
            status=status,
            reference_artifact_path=reference_artifact_path,
            analysis_grid_contract_path=analysis_grid_contract_path,
            acquisition_authority_receipt_path=acquisition_authority_receipt_path,
            reference_authority_decision_path=reference_authority_decision_path,
            reference_authority_signature_path=reference_authority_signature_path,
            reference_authority_public_keys=reference_authority_public_keys,
            observation_start=observation_start,
            observation_end=observation_end,
            reference_product_id=reference_product_id,
        )
        if experiment_id is not None and experiment_id != acquisition.experiment_id:
            raise QualifiedReferenceReleaseError(
                "experiment_id differs from the verified acquisition assessment."
            )
        payload = _base_payload(
            release_id=release_identifier,
            release_status=status,
            dataset_mode="candidate",
            study_area_id=area_identifier,
            study_area_name=acquisition.study_area,
            event_id=event_identifier,
            experiment_id=acquisition.experiment_id,
            source_timestamp=source_time,
            generated_at=generated,
            confidence_class="low",
            source_name=name,
            assumptions=normalized_assumptions,
            data_version=version,
            git_commit=commit,
            evidence_classification=_classification(
                authority_class=authority_class,
                status=status,
            ),
            source_permissions=_false_permissions(),
            purpose=selected_purpose,
            purpose_authorizations=_purpose_authorizations(
                selected_purpose,
                status,
                None,
            ),
            reference_artifact=None,
            analysis_grid=None,
            acquisition_lineage=_acquisition_lineage(acquisition),
            evidence_bundle_sha256=None,
            processing_allowed=False,
            eligible_for_development=False,
            eligible_for_evaluation=False,
            synthetic_processing_allowed=False,
            blockers=tuple(sorted(set(acquisition.blockers))),
        )
        return _seal_and_validate(payload)

    if status == SYNTHETIC_STATUS:
        if acquisition is not None:
            raise QualifiedReferenceReleaseError(
                "Synthetic fixtures must not carry a real acquisition assessment."
            )
        if acquisition_authority_receipt_path is not None:
            raise QualifiedReferenceReleaseError(
                "Synthetic fixtures must not carry an acquisition-authority receipt."
            )
        if (
            reference_authority_decision_path is not None
            or reference_authority_signature_path is not None
            or reference_authority_public_keys
        ):
            raise QualifiedReferenceReleaseError(
                "Synthetic fixtures must not carry Reference Authority evidence."
            )
        if authority_class != "synthetic_fixture":
            raise QualifiedReferenceReleaseError(
                "Synthetic releases require reference_authority_class="
                "'synthetic_fixture'."
            )
        synthetic_experiment = _identifier(experiment_id, "experiment_id")
        product_id = _identifier(reference_product_id, "reference_product_id")
        start = _timestamp(observation_start, "observation_start")
        end = _timestamp(observation_end, "observation_end")
        artifact, grid = _verified_artifact_and_grid(
            reference_artifact_path,
            analysis_grid_contract_path,
            product_id=product_id,
            observation_start=start,
            observation_end=end,
            source_timestamp=source_time,
        )
        permissions = _synthetic_permissions()
        lineage = _synthetic_lineage()
        evidence_hash = _evidence_bundle_sha256(
            artifact=artifact,
            grid=grid,
            lineage=lineage,
            permissions=permissions,
            classification=_classification(
                authority_class=authority_class,
                status=status,
            ),
            purpose=selected_purpose,
        )
        payload = _base_payload(
            release_id=release_identifier,
            release_status=status,
            dataset_mode="fixture_demo",
            study_area_id=area_identifier,
            study_area_name=area_identifier,
            event_id=event_identifier,
            experiment_id=synthetic_experiment,
            source_timestamp=source_time,
            generated_at=generated,
            confidence_class="low",
            source_name=name,
            assumptions=normalized_assumptions,
            data_version=version,
            git_commit=commit,
            evidence_classification=_classification(
                authority_class=authority_class,
                status=status,
            ),
            source_permissions=permissions,
            purpose=selected_purpose,
            purpose_authorizations=_purpose_authorizations(
                selected_purpose,
                status,
                evidence_hash,
            ),
            reference_artifact=artifact,
            analysis_grid=grid,
            acquisition_lineage=lineage,
            evidence_bundle_sha256=evidence_hash,
            processing_allowed=False,
            eligible_for_development=False,
            eligible_for_evaluation=False,
            synthetic_processing_allowed=True,
            blockers=(SYNTHETIC_LIMITATION,),
        )
        _require_unchanged_evidence_file(
            reference_artifact_path,
            artifact["sha256"],
            "reference artifact",
        )
        _require_unchanged_evidence_file(
            analysis_grid_contract_path,
            grid["sha256"],
            "analysis-grid contract",
        )
        return _seal_and_validate(payload)

    if acquisition is None:
        raise QualifiedReferenceReleaseError(
            "Qualified output requires a ready signed acquisition assessment."
        )
    _require_acquisition(acquisition)
    if not acquisition.ready or acquisition.blockers:
        raise QualifiedReferenceReleaseError(
            "Qualified output is impossible without a ready signed acquisition "
            "assessment."
        )
    if authority_class not in QUALIFIED_AUTHORITY_CLASSES:
        raise QualifiedReferenceReleaseError(
            "Qualified output requires observed-event or expert-interpretation "
            "authority classification."
        )
    if confidence_class not in {"medium", "high"}:
        raise QualifiedReferenceReleaseError(
            "Qualified output requires medium or high confidence."
        )
    if experiment_id is not None and experiment_id != acquisition.experiment_id:
        raise QualifiedReferenceReleaseError(
            "experiment_id differs from the verified acquisition assessment."
        )

    authority = _qualified_authority_binding(
        acquisition,
        acquisition_authority_receipt_path,
        generated_at=generated,
    )
    reference = authority["reference"]
    if name != reference["source_name"]:
        raise QualifiedReferenceReleaseError(
            "source_name differs from the signed reference authorization."
        )
    if _format_utc(source_time) != reference["source_timestamp"]:
        raise QualifiedReferenceReleaseError(
            "source_timestamp differs from the signed reference authorization."
        )
    requested_product_id = (
        reference["product_id"]
        if reference_product_id is None
        else _identifier(reference_product_id, "reference_product_id")
    )
    if requested_product_id != reference["product_id"]:
        raise QualifiedReferenceReleaseError(
            "reference_product_id differs from the signed authorization."
        )
    artifact, grid = _verified_artifact_and_grid(
        reference_artifact_path,
        analysis_grid_contract_path,
        product_id=requested_product_id,
        observation_start=_timestamp(
            reference["acquisition_start_utc"],
            "signed reference acquisition_start_utc",
        ),
        observation_end=_timestamp(
            reference["acquisition_end_utc"],
            "signed reference acquisition_end_utc",
        ),
        source_timestamp=source_time,
    )
    if artifact["sha256"] != reference["artifact_sha256"]:
        raise QualifiedReferenceReleaseError(
            "Reference artifact bytes differ from the signed authorization."
        )
    if artifact["sha256"] != acquisition.reference_mask_sha256:
        raise QualifiedReferenceReleaseError(
            "Reference artifact bytes differ from the verified acquisition manifest."
        )
    permissions = _qualified_permissions(reference["permissions"])
    reference_authority = _validate_reference_authority_decision(
        decision_path=reference_authority_decision_path,
        signature_path=reference_authority_signature_path,
        trusted_public_keys=reference_authority_public_keys,
        legal_authority_receipt=authority["payload"],
        event_id=event_identifier,
        study_area_id=area_identifier,
        experiment_id=acquisition.experiment_id,
        source_name=name,
        product_id=requested_product_id,
        artifact_sha256=artifact["sha256"],
        source_timestamp=source_time,
        observation_start=_timestamp(
            artifact["observation_start"],
            "reference observation_start",
        ),
        observation_end=_timestamp(
            artifact["observation_end"],
            "reference observation_end",
        ),
        reference_authority_class=authority_class,
        purpose=selected_purpose,
        generated_at=generated,
    )
    lineage = _acquisition_lineage(
        acquisition,
        reference_authorization=reference,
        reference_authority_receipt=reference_authority,
    )
    classification = _classification(
        authority_class=authority_class,
        status=status,
    )
    evidence_hash = _evidence_bundle_sha256(
        artifact=artifact,
        grid=grid,
        lineage=lineage,
        permissions=permissions,
        classification=classification,
        purpose=selected_purpose,
    )
    eligible_for_development, eligible_for_evaluation = _purpose_eligibility(
        selected_purpose
    )
    payload = _base_payload(
        release_id=release_identifier,
        release_status=status,
        dataset_mode="candidate",
        study_area_id=area_identifier,
        study_area_name=acquisition.study_area,
        event_id=event_identifier,
        experiment_id=acquisition.experiment_id,
        source_timestamp=source_time,
        generated_at=generated,
        confidence_class=confidence_class,
        source_name=name,
        assumptions=normalized_assumptions,
        data_version=version,
        git_commit=commit,
        evidence_classification=classification,
        source_permissions=permissions,
        purpose=selected_purpose,
        purpose_authorizations=_purpose_authorizations(
            selected_purpose,
            status,
            evidence_hash,
        ),
        reference_artifact=artifact,
        analysis_grid=grid,
        acquisition_lineage=lineage,
        evidence_bundle_sha256=evidence_hash,
        processing_allowed=True,
        eligible_for_development=eligible_for_development,
        eligible_for_evaluation=eligible_for_evaluation,
        synthetic_processing_allowed=False,
        blockers=(),
    )
    _require_unchanged_evidence_file(
        acquisition_authority_receipt_path,
        acquisition.authority_receipt_sha256,
        "acquisition-authority receipt",
    )
    _require_unchanged_evidence_file(
        reference_artifact_path,
        artifact["sha256"],
        "reference artifact",
    )
    _require_unchanged_evidence_file(
        analysis_grid_contract_path,
        grid["sha256"],
        "analysis-grid contract",
    )
    _require_unchanged_evidence_file(
        reference_authority_decision_path,
        reference_authority["reference_authority_decision_file_sha256"],
        "Reference Authority decision",
    )
    _require_unchanged_evidence_file(
        reference_authority_signature_path,
        reference_authority["reference_authority_signature_file_sha256"],
        "Reference Authority signature",
    )
    return _seal_and_validate(payload)


def validate_qualified_reference_release(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate structure, hashes, state semantics, safety, and path hygiene."""

    value = dict(payload)
    _exact_keys(value, _ROOT_KEYS, "qualified reference release")
    if value["schema_version"] != SCHEMA_VERSION:
        raise QualifiedReferenceReleaseError("Unsupported schema_version.")
    if value["artifact_schema"] != RELEASE_SCHEMA:
        raise QualifiedReferenceReleaseError("Unsupported artifact_schema.")
    _identifier(value["release_id"], "release_id")
    status = _choice(value["release_status"], RELEASE_STATUSES, "release_status")
    if value["operational_status"] != "non_operational":
        raise QualifiedReferenceReleaseError(
            "Qualified-reference releases are always non-operational."
        )
    if value["dataset_mode"] not in {"fixture_demo", "candidate"}:
        raise QualifiedReferenceReleaseError("dataset_mode is invalid.")
    _identifier(value["study_area_id"], "study_area_id")
    _text(value["study_area_name"], "study_area_name")
    _identifier(value["event_id"], "event_id")
    _identifier(value["experiment_id"], "experiment_id")
    source_time = _timestamp(value["source_timestamp"], "source_timestamp")
    generated = _timestamp(value["generated_at"], "generated_at")
    if source_time > generated:
        raise QualifiedReferenceReleaseError(
            "source_timestamp cannot be later than generated_at."
        )
    if value["confidence_class"] not in {"low", "medium", "high"}:
        raise QualifiedReferenceReleaseError("confidence_class is invalid.")
    _text(value["source_name"], "source_name")
    _assumptions(value["assumptions"])
    _identifier(value["data_version"], "data_version")
    _commit(value["git_commit"])

    if (
        value["official_warning"] is not False
        or value["can_feed_decision_layer"] is not False
        or value["can_feed_fpps"] is not False
        or value["can_assign_action_class"] is not False
        or value["agency_operational_authorized"] is not False
    ):
        raise QualifiedReferenceReleaseError(
            "Qualified-reference release contains unsafe authority flags."
        )
    if value["downstream_experiment_gate_required"] is not True:
        raise QualifiedReferenceReleaseError(
            "A separate downstream experiment gate must remain required."
        )
    if tuple(value["safety_limitations"]) != SAFETY_LIMITATIONS:
        raise QualifiedReferenceReleaseError("Safety limitations were weakened.")

    classification = _validate_classification(value["evidence_classification"])
    permissions = _validate_permissions(value["source_permissions"])
    purpose = _choice(value["purpose"], frozenset(PURPOSES), "purpose")
    purposes = _validate_purposes(
        value["purpose_authorizations"],
        selected_purpose=purpose,
    )
    lineage = _validate_lineage(value["acquisition_lineage"])
    blockers = _string_list(value["blockers"], "blockers", allow_empty=True)
    if value["reason_blocked"] != "; ".join(blockers):
        raise QualifiedReferenceReleaseError(
            "reason_blocked must be the deterministic blocker join."
        )

    artifact = value["reference_artifact"]
    grid = value["analysis_grid"]
    if artifact is not None:
        artifact = _validate_artifact_record(artifact)
    if grid is not None:
        grid = _validate_grid_record(grid)
    if (artifact is None) != (grid is None):
        raise QualifiedReferenceReleaseError(
            "Reference artifact and analysis grid must be present together."
        )
    if artifact is not None:
        _validate_artifact_grid_compatibility(
            artifact,
            grid,
            source_timestamp=source_time,
        )

    _validate_status_semantics(
        value,
        status=status,
        classification=classification,
        permissions=permissions,
        purpose=purpose,
        purposes=purposes,
        lineage=lineage,
        artifact=artifact,
        grid=grid,
        blockers=blockers,
        generated_at=generated,
    )
    _reject_private_paths(value)

    expected_release_sha = _canonical_sha256(
        {key: item for key, item in value.items() if key != "release_sha256"}
    )
    if value["release_sha256"] != expected_release_sha:
        raise QualifiedReferenceReleaseError("Release self-hash mismatch.")
    return value


def write_qualified_reference_release(
    payload: Mapping[str, Any],
    output_path: str | Path,
) -> Path:
    """Write a validated release exactly once."""

    value = validate_qualified_reference_release(payload)
    target = Path(output_path)
    if target.suffix.lower() != ".json":
        raise QualifiedReferenceReleaseError("Release output must be a JSON file.")
    if target.exists():
        raise QualifiedReferenceReleaseError(
            f"Release output already exists and is immutable: {target}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
    except FileExistsError as exc:
        raise QualifiedReferenceReleaseError(
            f"Release output appeared during write and will not be replaced: {target}"
        ) from exc
    return target


def load_qualified_reference_release(path: str | Path) -> dict[str, Any]:
    """Load and validate one release JSON."""

    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QualifiedReferenceReleaseError(
            f"Cannot load qualified-reference release: {exc}"
        ) from exc
    if not isinstance(value, Mapping):
        raise QualifiedReferenceReleaseError("Release JSON root must be an object.")
    return validate_qualified_reference_release(value)


def _base_payload(
    *,
    release_id: str,
    release_status: str,
    dataset_mode: str,
    study_area_id: str,
    study_area_name: str,
    event_id: str,
    experiment_id: str,
    source_timestamp: datetime,
    generated_at: datetime,
    confidence_class: str,
    source_name: str,
    assumptions: tuple[str, ...],
    data_version: str,
    git_commit: str,
    evidence_classification: Mapping[str, Any],
    source_permissions: Mapping[str, bool],
    purpose: str,
    purpose_authorizations: Sequence[Mapping[str, Any]],
    reference_artifact: Mapping[str, Any] | None,
    analysis_grid: Mapping[str, Any] | None,
    acquisition_lineage: Mapping[str, Any],
    evidence_bundle_sha256: str | None,
    processing_allowed: bool,
    eligible_for_development: bool,
    eligible_for_evaluation: bool,
    synthetic_processing_allowed: bool,
    blockers: Sequence[str],
) -> dict[str, Any]:
    normalized_blockers = tuple(sorted(set(blockers)))
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_schema": RELEASE_SCHEMA,
        "release_id": release_id,
        "release_status": release_status,
        "dataset_mode": dataset_mode,
        "operational_status": "non_operational",
        "study_area_id": study_area_id,
        "study_area_name": study_area_name,
        "event_id": event_id,
        "experiment_id": experiment_id,
        "source_timestamp": _format_utc(source_timestamp),
        "generated_at": _format_utc(generated_at),
        "confidence_class": confidence_class,
        "source_name": source_name,
        "assumptions": list(assumptions),
        "data_version": data_version,
        "git_commit": git_commit,
        "official_warning": False,
        "evidence_classification": dict(evidence_classification),
        "source_permissions": dict(source_permissions),
        "purpose": purpose,
        "purpose_authorizations": [dict(item) for item in purpose_authorizations],
        "reference_artifact": (
            dict(reference_artifact) if reference_artifact is not None else None
        ),
        "analysis_grid": dict(analysis_grid) if analysis_grid is not None else None,
        "acquisition_lineage": dict(acquisition_lineage),
        "evidence_bundle_sha256": evidence_bundle_sha256,
        "processing_allowed": processing_allowed,
        "eligible_for_controlled_model_development": eligible_for_development,
        "eligible_for_controlled_model_evaluation": eligible_for_evaluation,
        "synthetic_fixture_processing_allowed": synthetic_processing_allowed,
        "downstream_experiment_gate_required": True,
        "can_feed_decision_layer": False,
        "can_feed_fpps": False,
        "can_assign_action_class": False,
        "agency_operational_authorized": False,
        "safety_limitations": list(SAFETY_LIMITATIONS),
        "blockers": list(normalized_blockers),
        "reason_blocked": "; ".join(normalized_blockers),
    }


def _seal_and_validate(payload: dict[str, Any]) -> dict[str, Any]:
    _reject_private_paths(payload)
    payload["release_sha256"] = _canonical_sha256(payload)
    return validate_qualified_reference_release(payload)


def _classification(*, authority_class: str, status: str) -> dict[str, str]:
    if status == BLOCKED_STATUS:
        return {
            "reference_authority_class": authority_class,
            "qualification_status": "blocked_not_qualified",
            "rights_evidence_status": "missing_or_unverified",
            "independence_status": "not_established",
            "purpose_acceptance_status": "blocked",
            "field_validation_status": "not_claimed",
        }
    if status == SYNTHETIC_STATUS:
        return {
            "reference_authority_class": "synthetic_fixture",
            "qualification_status": "synthetic_fixture_only",
            "rights_evidence_status": "project_owned_synthetic_fixture",
            "independence_status": "not_applicable_synthetic_fixture",
            "purpose_acceptance_status": "synthetic_fixture_only",
            "field_validation_status": "not_claimed",
        }
    return {
        "reference_authority_class": authority_class,
        "qualification_status": "qualified_expert_or_adjudicated",
        "rights_evidence_status": "externally_verified_product_specific",
        "independence_status": "independent_of_model_inputs",
        "purpose_acceptance_status": "exact_purpose_authority_verified",
        "field_validation_status": "not_claimed",
    }


def _purpose_authorizations(
    purpose: str,
    status: str,
    evidence_sha256: str | None,
) -> list[dict[str, Any]]:
    if status == BLOCKED_STATUS:
        purpose_status = PURPOSE_BLOCKED
        authority_basis = "none"
    elif status == SYNTHETIC_STATUS:
        purpose_status = PURPOSE_SYNTHETIC
        authority_basis = "project_owned_synthetic_fixture"
    else:
        purpose_status = PURPOSE_QUALIFIED
        authority_basis = (
            "verified_external_product_authority_and_scientific_qualification"
        )
    return [
        {
            "purpose": purpose,
            "status": purpose_status,
            "authority_basis": authority_basis,
            "evidence_sha256": evidence_sha256,
        }
    ]


def _purpose_eligibility(purpose: str) -> tuple[bool, bool]:
    """Return exact model-development and final-evaluation eligibility."""

    return (
        purpose
        in {
            "flood_model_training_labels",
            "model_probability_calibration",
        },
        purpose == "model_final_evaluation",
    )


def _false_permissions() -> dict[str, bool]:
    return {field: False for field in EXTERNAL_PERMISSION_FIELDS}


def _synthetic_permissions() -> dict[str, bool]:
    return {field: True for field in EXTERNAL_PERMISSION_FIELDS}


def _qualified_permissions(value: Any) -> dict[str, bool]:
    if not isinstance(value, Mapping):
        raise QualifiedReferenceReleaseError(
            "Signed reference permissions must be an object."
        )
    if set(value) != set(EXTERNAL_PERMISSION_FIELDS):
        raise QualifiedReferenceReleaseError(
            "Signed reference permissions do not match the controlled contract."
        )
    permissions: dict[str, bool] = {}
    for field in EXTERNAL_PERMISSION_FIELDS:
        raw = value[field]
        if not isinstance(raw, bool):
            raise QualifiedReferenceReleaseError(
                f"Signed reference permission {field} must be boolean."
            )
        permissions[field] = raw
    always_required = set(EXTERNAL_PERMISSION_FIELDS) - {"source_redistribution"}
    if any(permissions[field] is not True for field in always_required):
        raise QualifiedReferenceReleaseError(
            "Every required purpose-specific reference permission must be true."
        )
    return permissions


def _reference_authority_lineage_fields() -> tuple[str, ...]:
    return (
        "reference_authority_decision_id",
        "reference_authority_decision_sha256",
        "reference_authority_decision_file_sha256",
        "reference_authority_signature_sha256",
        "reference_authority_signature_file_sha256",
        "reference_authority_signing_key_id",
        "reference_authority_public_key_sha256",
        "reference_authority_id",
        "reference_authority_issued_at_utc",
        "reference_authority_expires_at_utc",
        "reference_authority_purpose",
        "reference_authority_class",
        "reference_authority_receipt_sha256",
    )


def _empty_reference_authority_lineage() -> dict[str, None]:
    return {field: None for field in _reference_authority_lineage_fields()}


def _acquisition_lineage(
    acquisition: AcquisitionGateAssessment,
    *,
    reference_authorization: Mapping[str, Any] | None = None,
    reference_authority_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    _require_acquisition(acquisition)
    role_hashes = {role: digest or None for role, digest in acquisition.sha256_by_role}
    if set(role_hashes) != {"pre_event_sar", "post_event_sar", "reference_mask"}:
        raise QualifiedReferenceReleaseError(
            "Acquisition role hashes are incomplete or substituted."
        )
    reference_binding: dict[str, Any]
    if reference_authorization is None:
        reference_binding = {
            "reference_authorization_sha256": None,
            "reference_product_id": None,
            "reference_source_name": None,
            "reference_source_timestamp": None,
            "reference_observation_start": None,
            "reference_observation_end": None,
            "reference_permissions_sha256": None,
        }
    else:
        permissions = _qualified_permissions(reference_authorization.get("permissions"))
        reference_binding = {
            "reference_authorization_sha256": _canonical_sha256(
                dict(reference_authorization)
            ),
            "reference_product_id": _identifier(
                reference_authorization.get("product_id"),
                "signed reference product_id",
            ),
            "reference_source_name": _text(
                reference_authorization.get("source_name"),
                "signed reference source_name",
            ),
            "reference_source_timestamp": _format_utc(
                _timestamp(
                    reference_authorization.get("source_timestamp"),
                    "signed reference source_timestamp",
                )
            ),
            "reference_observation_start": _format_utc(
                _timestamp(
                    reference_authorization.get("acquisition_start_utc"),
                    "signed reference acquisition_start_utc",
                )
            ),
            "reference_observation_end": _format_utc(
                _timestamp(
                    reference_authorization.get("acquisition_end_utc"),
                    "signed reference acquisition_end_utc",
                )
            ),
            "reference_permissions_sha256": _canonical_sha256(permissions),
        }
    if reference_authority_receipt is None:
        scientific_binding = _empty_reference_authority_lineage()
    else:
        scientific_binding = {
            key: reference_authority_receipt[key]
            for key in _reference_authority_lineage_fields()
        }
    return {
        "assessment_status": "ready" if acquisition.ready else "blocked",
        "acquisition_manifest_sha256": acquisition.manifest_sha256,
        "acquisition_manifest_file_sha256": acquisition.manifest_file_sha256,
        "acquisition_authority_receipt_sha256": (acquisition.authority_receipt_sha256),
        "authority_signing_key_id": acquisition.authority_signing_key_id,
        "authority_issued_at_utc": (
            _format_utc(acquisition.authority_issued_at_utc)
            if acquisition.authority_issued_at_utc is not None
            else None
        ),
        "authority_expires_at_utc": (
            _format_utc(acquisition.authority_expires_at_utc)
            if acquisition.authority_expires_at_utc is not None
            else None
        ),
        "external_authority_decision_sha256": (
            acquisition.external_authority_decision_sha256
        ),
        "external_authority_signing_key_id": (
            acquisition.external_authority_signing_key_id
        ),
        **reference_binding,
        **scientific_binding,
        "sha256_by_role": role_hashes,
        "assessment_blockers": list(sorted(set(acquisition.blockers))),
    }


def _synthetic_lineage() -> dict[str, Any]:
    return {
        "assessment_status": "not_applicable_synthetic_fixture",
        "acquisition_manifest_sha256": None,
        "acquisition_manifest_file_sha256": None,
        "acquisition_authority_receipt_sha256": None,
        "authority_signing_key_id": None,
        "authority_issued_at_utc": None,
        "authority_expires_at_utc": None,
        "external_authority_decision_sha256": None,
        "external_authority_signing_key_id": None,
        "reference_authorization_sha256": None,
        "reference_product_id": None,
        "reference_source_name": None,
        "reference_source_timestamp": None,
        "reference_observation_start": None,
        "reference_observation_end": None,
        "reference_permissions_sha256": None,
        **_empty_reference_authority_lineage(),
        "sha256_by_role": {
            "pre_event_sar": None,
            "post_event_sar": None,
            "reference_mask": None,
        },
        "assessment_blockers": [],
    }


def _qualified_authority_binding(
    acquisition: AcquisitionGateAssessment,
    receipt_path: str | Path | None,
    *,
    generated_at: datetime,
) -> dict[str, Any]:
    if receipt_path is None:
        raise QualifiedReferenceReleaseError(
            "Qualified output requires the exact acquisition-authority receipt."
        )
    required_lineage = (
        acquisition.authority_receipt_sha256,
        acquisition.authority_signing_key_id,
        acquisition.authority_issued_at_utc,
        acquisition.authority_expires_at_utc,
        acquisition.external_authority_decision_sha256,
        acquisition.external_authority_signing_key_id,
    )
    if any(item is None for item in required_lineage):
        raise QualifiedReferenceReleaseError(
            "Ready acquisition lacks complete signed authority lineage."
        )
    assert acquisition.authority_issued_at_utc is not None
    assert acquisition.authority_expires_at_utc is not None
    if not (
        acquisition.authority_issued_at_utc
        <= generated_at
        <= acquisition.authority_expires_at_utc
    ):
        raise QualifiedReferenceReleaseError(
            "Release time is outside acquisition-authority validity."
        )
    receipt = Path(receipt_path)
    receipt_bytes = _stable_file_bytes(
        receipt,
        "acquisition-authority receipt",
    )
    receipt_sha = hashlib.sha256(receipt_bytes).hexdigest()
    if receipt_sha != acquisition.authority_receipt_sha256:
        raise QualifiedReferenceReleaseError(
            "Acquisition-authority receipt bytes were substituted."
        )
    try:
        payload = json.loads(receipt_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QualifiedReferenceReleaseError(
            f"Cannot read acquisition-authority receipt: {exc}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise QualifiedReferenceReleaseError(
            "Acquisition-authority receipt root must be an object."
        )
    expected = {
        "experiment_id": acquisition.experiment_id,
        "study_area": acquisition.study_area,
        "acquisition_manifest_sha256": acquisition.manifest_sha256,
        "signing_key_id": acquisition.authority_signing_key_id,
        "external_authority_decision_sha256": (
            acquisition.external_authority_decision_sha256
        ),
        "external_authority_signing_key_id": (
            acquisition.external_authority_signing_key_id
        ),
        "issued_at_utc": _format_utc(acquisition.authority_issued_at_utc),
        "expires_at_utc": _format_utc(acquisition.authority_expires_at_utc),
    }
    for field, expected_value in expected.items():
        if payload.get(field) != expected_value:
            raise QualifiedReferenceReleaseError(
                f"Acquisition-authority receipt {field} was substituted."
            )
    _sha256(
        payload.get("manifest_sha256"),
        "acquisition-authority receipt self-hash",
    )
    if (
        payload.get("official_warning") is not False
        or payload.get("can_feed_decision_layer") is not False
    ):
        raise QualifiedReferenceReleaseError(
            "Acquisition-authority receipt contains unsafe authority flags."
        )
    authorizations = payload.get("authorizations")
    if not isinstance(authorizations, list):
        raise QualifiedReferenceReleaseError(
            "Acquisition-authority authorizations must be a list."
        )
    references = [
        item
        for item in authorizations
        if isinstance(item, Mapping) and item.get("role") == "reference_mask"
    ]
    if len(references) != 1:
        raise QualifiedReferenceReleaseError(
            "Acquisition authority must contain exactly one reference_mask row."
        )
    reference = dict(references[0])
    required_reference_fields = {
        "source_name",
        "product_id",
        "source_timestamp",
        "acquisition_start_utc",
        "acquisition_end_utc",
        "artifact_sha256",
        "permissions",
        "reference_qualification",
        "reference_mask_status",
        "temporal_alignment_status",
        "authority_decision",
    }
    missing = sorted(required_reference_fields - set(reference))
    if missing:
        raise QualifiedReferenceReleaseError(
            f"Signed reference authorization lacks fields: {missing}."
        )
    _text(reference["source_name"], "signed reference source_name")
    _identifier(reference["product_id"], "signed reference product_id")
    _sha256(reference["artifact_sha256"], "signed reference artifact_sha256")
    qualification = reference["reference_qualification"]
    if not isinstance(qualification, Mapping):
        raise QualifiedReferenceReleaseError(
            "Signed reference qualification must be an object."
        )
    if (
        qualification.get("status") != "qualified_expert_or_adjudicated"
        or qualification.get("independent_of_model_inputs") is not True
        or reference["reference_mask_status"] != "qualified_expert_or_adjudicated"
        or reference["temporal_alignment_status"] != "confirmed"
        or reference["authority_decision"] != "approved_for_controlled_experiment"
    ):
        raise QualifiedReferenceReleaseError(
            "Signed reference is not independently qualified for the requested purpose."
        )
    _qualified_permissions(reference["permissions"])
    return {"payload": dict(payload), "reference": reference}


def _validate_reference_authority_decision(
    *,
    decision_path: str | Path | None,
    signature_path: str | Path | None,
    trusted_public_keys: Mapping[str, bytes] | None,
    legal_authority_receipt: Mapping[str, Any],
    event_id: str,
    study_area_id: str,
    experiment_id: str,
    source_name: str,
    product_id: str,
    artifact_sha256: str,
    source_timestamp: datetime,
    observation_start: datetime,
    observation_end: datetime,
    reference_authority_class: str,
    purpose: str,
    generated_at: datetime,
) -> dict[str, Any]:
    """Validate a separate, purpose-specific scientific authority decision."""

    if decision_path is None or signature_path is None:
        raise QualifiedReferenceReleaseError(
            "Qualified output requires a file-backed Reference Authority "
            "decision and detached signature."
        )
    if not isinstance(trusted_public_keys, Mapping) or not trusted_public_keys:
        raise QualifiedReferenceReleaseError(
            "Reference Authority public key must come from runtime trust configuration."
        )
    decision_bytes = _stable_file_bytes(
        Path(decision_path),
        "Reference Authority decision",
    )
    signature_file_bytes = _stable_file_bytes(
        Path(signature_path),
        "Reference Authority signature",
    )
    try:
        decision = json.loads(decision_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QualifiedReferenceReleaseError(
            f"Reference Authority decision is not valid JSON: {exc}"
        ) from exc
    if not isinstance(decision, Mapping):
        raise QualifiedReferenceReleaseError(
            "Reference Authority decision root must be an object."
        )
    _exact_keys(
        decision,
        _REFERENCE_AUTHORITY_DECISION_KEYS,
        "Reference Authority decision",
    )
    if decision["schema_version"] != REFERENCE_AUTHORITY_DECISION_SCHEMA:
        raise QualifiedReferenceReleaseError(
            "Reference Authority decision schema is unsupported."
        )
    if decision["decision_status"] != "approved_for_exact_purpose":
        raise QualifiedReferenceReleaseError(
            "Reference Authority decision is not purpose-approved."
        )
    expected = {
        "event_id": event_id,
        "study_area_id": study_area_id,
        "experiment_id": experiment_id,
        "source_name": source_name,
        "product_id": product_id,
        "artifact_sha256": artifact_sha256,
        "source_timestamp": _format_utc(source_timestamp),
        "observation_start": _format_utc(observation_start),
        "observation_end": _format_utc(observation_end),
        "reference_authority_class": reference_authority_class,
        "purpose": purpose,
    }
    for field, expected_value in expected.items():
        if decision[field] != expected_value:
            raise QualifiedReferenceReleaseError(
                f"Reference Authority decision {field} was substituted."
            )
    _identifier(decision["decision_id"], "Reference Authority decision_id")
    if reference_authority_class not in QUALIFIED_AUTHORITY_CLASSES:
        raise QualifiedReferenceReleaseError(
            "Reference Authority class is not qualified."
        )
    if decision["independent_of_model_inputs"] is not True:
        raise QualifiedReferenceReleaseError(
            "Reference Authority did not attest scientific independence."
        )
    _text(decision["scientific_method"], "Reference Authority scientific_method")
    _text(
        decision["known_uncertainty_and_error_categories"],
        "Reference Authority known uncertainty",
    )
    if (
        decision["official_warning"] is not False
        or decision["can_feed_decision_layer"] is not False
        or decision["can_feed_fpps"] is not False
        or decision["can_assign_action_class"] is not False
    ):
        raise QualifiedReferenceReleaseError(
            "Reference Authority decision contains unsafe downstream authority."
        )
    issued = _timestamp(
        decision["issued_at_utc"],
        "Reference Authority issued_at_utc",
    )
    expires = _timestamp(
        decision["expires_at_utc"],
        "Reference Authority expires_at_utc",
    )
    if (
        expires <= issued
        or issued < observation_end
        or not issued <= generated_at <= expires
    ):
        raise QualifiedReferenceReleaseError(
            "Reference Authority decision is premature, expired, or not yet valid."
        )
    signer = decision["signer"]
    if not isinstance(signer, Mapping):
        raise QualifiedReferenceReleaseError(
            "Reference Authority signer must be an object."
        )
    _exact_keys(
        signer,
        _REFERENCE_AUTHORITY_SIGNER_KEYS,
        "Reference Authority signer",
    )
    signer_name = _text(signer["name"], "Reference Authority signer name")
    signer_org = _text(
        signer["organization"],
        "Reference Authority signer organization",
    )
    _text(signer["title_or_role"], "Reference Authority signer title_or_role")
    _text(signer["authority_basis"], "Reference Authority authority_basis")
    _text(
        signer["identity_evidence_type"],
        "Reference Authority identity_evidence_type",
    )
    _sha256(
        signer["identity_evidence_sha256"],
        "Reference Authority identity_evidence_sha256",
    )
    key_id = _identifier(
        signer["signing_key_id"],
        "Reference Authority signing_key_id",
    )
    key_value = trusted_public_keys.get(key_id)
    if key_value is None:
        raise QualifiedReferenceReleaseError(
            "Reference Authority signing key is not trusted at runtime."
        )
    try:
        public_key = controlled._validated_ed25519_public_key(key_value)
    except Exception as exc:
        raise QualifiedReferenceReleaseError(
            f"Reference Authority runtime public key is invalid: {exc}"
        ) from exc
    public_key_sha256 = hashlib.sha256(public_key).hexdigest()
    if signer["public_key_sha256"] != public_key_sha256:
        raise QualifiedReferenceReleaseError(
            "Reference Authority public-key fingerprint was substituted."
        )
    legal_decision = legal_authority_receipt.get("external_authority_decision")
    if not isinstance(legal_decision, Mapping):
        raise QualifiedReferenceReleaseError(
            "Legal authority receipt lacks its external decision."
        )
    legal_signer = legal_decision.get("authorized_signer")
    if not isinstance(legal_signer, Mapping):
        raise QualifiedReferenceReleaseError(
            "Legal authority receipt lacks signer identity."
        )
    legal_identity = (
        f"{_text(legal_signer.get('organization'), 'legal signer organization')}"
        f"::{_text(legal_signer.get('name'), 'legal signer name')}"
    )
    authority_id = f"{signer_org}::{signer_name}"
    legal_key_ids = {
        legal_signer.get("signing_key_id"),
        legal_authority_receipt.get("signing_key_id"),
        legal_authority_receipt.get("external_authority_signing_key_id"),
    }
    if (
        authority_id == legal_identity
        or key_id in legal_key_ids
        or public_key_sha256 == legal_signer.get("public_key_sha256")
    ):
        raise QualifiedReferenceReleaseError(
            "Reference Authority identity and credential must be distinct from "
            "acquisition/legal authority."
        )
    try:
        signature = controlled._decode_ed25519_material(
            signature_file_bytes.decode("ascii").strip(),
            expected_length=64,
            label="Reference Authority detached signature",
        )
    except Exception as exc:
        raise QualifiedReferenceReleaseError(
            f"Reference Authority signature encoding is invalid: {exc}"
        ) from exc
    if not controlled._ed25519_verify(
        public_key,
        signature,
        controlled._canonical_json_bytes(decision),
    ):
        raise QualifiedReferenceReleaseError(
            "Reference Authority detached Ed25519 signature is invalid."
        )
    receipt: dict[str, Any] = {
        "reference_authority_decision_id": decision["decision_id"],
        "reference_authority_decision_sha256": _canonical_sha256(decision),
        "reference_authority_decision_file_sha256": hashlib.sha256(
            decision_bytes
        ).hexdigest(),
        "reference_authority_signature_sha256": hashlib.sha256(signature).hexdigest(),
        "reference_authority_signature_file_sha256": hashlib.sha256(
            signature_file_bytes
        ).hexdigest(),
        "reference_authority_signing_key_id": key_id,
        "reference_authority_public_key_sha256": public_key_sha256,
        "reference_authority_id": authority_id,
        "reference_authority_issued_at_utc": _format_utc(issued),
        "reference_authority_expires_at_utc": _format_utc(expires),
        "reference_authority_purpose": purpose,
        "reference_authority_class": reference_authority_class,
    }
    receipt["reference_authority_receipt_sha256"] = _canonical_sha256(receipt)
    return receipt


def _verified_artifact_and_grid(
    artifact_path: str | Path | None,
    grid_path: str | Path | None,
    *,
    product_id: str,
    observation_start: datetime,
    observation_end: datetime,
    source_timestamp: datetime,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if artifact_path is None or grid_path is None:
        raise QualifiedReferenceReleaseError(
            "Reference artifact and analysis-grid contract are both required."
        )
    if observation_end < observation_start:
        raise QualifiedReferenceReleaseError(
            "Reference observation end precedes its start."
        )
    if not observation_start <= source_timestamp <= observation_end:
        raise QualifiedReferenceReleaseError(
            "source_timestamp is outside the reference observation interval."
        )
    grid = _load_analysis_grid(Path(grid_path))
    artifact = _inspect_reference_raster(
        Path(artifact_path),
        grid=grid,
        product_id=product_id,
        observation_start=observation_start,
        observation_end=observation_end,
    )
    return artifact, grid


def _load_analysis_grid(path: Path) -> dict[str, Any]:
    content = _stable_file_bytes(path, "analysis-grid contract")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise QualifiedReferenceReleaseError(
            f"Analysis-grid contract is not valid JSON: {exc}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise QualifiedReferenceReleaseError(
            "Analysis-grid contract root must be an object."
        )
    required = {"target_crs", "transform", "width", "height"}
    missing = sorted(required - set(payload))
    if missing:
        raise QualifiedReferenceReleaseError(
            f"Analysis-grid contract lacks fields: {missing}."
        )
    crs = _epsg(payload["target_crs"], "analysis-grid target_crs")
    _validate_equal_area_crs(crs)
    transform = _transform(payload["transform"], "analysis-grid transform")
    width = _positive_integer(payload["width"], "analysis-grid width")
    height = _positive_integer(payload["height"], "analysis-grid height")
    cell_size = [abs(transform[0]), abs(transform[4])]
    if not all(value > 0 for value in cell_size):
        raise QualifiedReferenceReleaseError(
            "Analysis-grid cell size must be positive."
        )
    return {
        "file_name": _safe_base_name(path.name, "analysis-grid file_name"),
        "sha256": hashlib.sha256(content).hexdigest(),
        "crs": crs,
        "transform": list(transform),
        "width": width,
        "height": height,
        "cell_size": cell_size,
    }


def _inspect_reference_raster(
    path: Path,
    *,
    grid: Mapping[str, Any],
    product_id: str,
    observation_start: datetime,
    observation_end: datetime,
) -> dict[str, Any]:
    if path.suffix.lower() not in {".tif", ".tiff"}:
        raise QualifiedReferenceReleaseError(
            "Reference artifact must be a GeoTIFF (.tif or .tiff)."
        )
    digest = _stable_file_sha256(path, "reference artifact")
    before = path.stat()
    try:
        import numpy as np
        import rasterio
    except ImportError as exc:  # pragma: no cover - exercised in minimal installs
        raise QualifiedReferenceReleaseError(
            "Reference-raster verification requires Rasterio and NumPy."
        ) from exc
    try:
        with rasterio.open(path) as dataset:
            if dataset.count != 1 or dataset.crs is None:
                raise QualifiedReferenceReleaseError(
                    "Reference artifact must be a single-band georeferenced raster."
                )
            crs = _epsg(dataset.crs.to_string(), "reference artifact CRS")
            if crs != grid["crs"]:
                raise QualifiedReferenceReleaseError(
                    "Reference artifact CRS differs from the analysis grid."
                )
            transform = tuple(float(item) for item in dataset.transform[:6])
            expected_transform = tuple(float(item) for item in grid["transform"])
            if any(
                not math.isclose(left, right, rel_tol=0.0, abs_tol=1e-12)
                for left, right in zip(transform, expected_transform, strict=True)
            ):
                raise QualifiedReferenceReleaseError(
                    "Reference artifact transform differs from the analysis grid."
                )
            if dataset.width != grid["width"] or dataset.height != grid["height"]:
                raise QualifiedReferenceReleaseError(
                    "Reference artifact dimensions differ from the analysis grid."
                )
            if dataset.nodata is None:
                raise QualifiedReferenceReleaseError(
                    "Reference artifact requires explicit nodata."
                )
            nodata = float(dataset.nodata)
            if not math.isfinite(nodata) or nodata in {0.0, 1.0}:
                raise QualifiedReferenceReleaseError(
                    "Reference nodata must be finite and distinct from classes 0/1."
                )
            observed_values: set[int] = set()
            for _block_index, window in dataset.block_windows(1):
                block = dataset.read(1, window=window)
                valid = block[block != dataset.nodata]
                if valid.size == 0:
                    continue
                if not np.isin(valid, [0, 1]).all():
                    raise QualifiedReferenceReleaseError(
                        "Reference valid pixels must contain only classes 0 and 1."
                    )
                observed_values.update(int(item) for item in np.unique(valid))
            if observed_values != {0, 1}:
                raise QualifiedReferenceReleaseError(
                    "Reference artifact must contain both non-flood (0) and flood (1)."
                )
            dtype = str(dataset.dtypes[0])
    except QualifiedReferenceReleaseError:
        raise
    except Exception as exc:
        raise QualifiedReferenceReleaseError(
            f"Reference artifact could not be verified safely: {exc}"
        ) from exc
    after = path.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise QualifiedReferenceReleaseError(
            "Reference artifact changed during verification."
        )
    return {
        "product_id": product_id,
        "file_name": _safe_base_name(path.name, "reference artifact file_name"),
        "sha256": digest,
        "media_type": "image/tiff; application=geotiff",
        "crs": grid["crs"],
        "transform": list(grid["transform"]),
        "width": grid["width"],
        "height": grid["height"],
        "band_count": 1,
        "dtype": dtype,
        "nodata": nodata,
        "valid_values": [0, 1],
        "observation_start": _format_utc(observation_start),
        "observation_end": _format_utc(observation_end),
        "covers_analysis_grid": True,
        "reprojection_performed": False,
    }


def _validate_status_semantics(
    value: Mapping[str, Any],
    *,
    status: str,
    classification: Mapping[str, str],
    permissions: Mapping[str, bool],
    purpose: str,
    purposes: Sequence[Mapping[str, Any]],
    lineage: Mapping[str, Any],
    artifact: Mapping[str, Any] | None,
    grid: Mapping[str, Any] | None,
    blockers: tuple[str, ...],
    generated_at: datetime,
) -> None:
    if status == BLOCKED_STATUS:
        if (
            value["dataset_mode"] != "candidate"
            or value["confidence_class"] != "low"
            or value["processing_allowed"] is not False
            or value["eligible_for_controlled_model_development"] is not False
            or value["eligible_for_controlled_model_evaluation"] is not False
            or value["synthetic_fixture_processing_allowed"] is not False
            or artifact is not None
            or grid is not None
            or value["evidence_bundle_sha256"] is not None
            or lineage["assessment_status"] != "blocked"
            or not lineage["assessment_blockers"]
            or any(
                lineage[field] is not None
                for field in (
                    "reference_authorization_sha256",
                    "reference_product_id",
                    "reference_source_name",
                    "reference_source_timestamp",
                    "reference_observation_start",
                    "reference_observation_end",
                    "reference_permissions_sha256",
                    *_reference_authority_lineage_fields(),
                )
            )
            or not blockers
            or set(blockers) != set(lineage["assessment_blockers"])
            or any(permissions.values())
            or any(item["status"] != PURPOSE_BLOCKED for item in purposes)
            or any(item["evidence_sha256"] is not None for item in purposes)
            or classification["qualification_status"] != "blocked_not_qualified"
        ):
            raise QualifiedReferenceReleaseError(
                "Blocked release attempts to carry qualified or processable state."
            )
        return

    if artifact is None or grid is None:
        raise QualifiedReferenceReleaseError(
            "Processable releases require artifact and grid evidence."
        )
    expected_evidence = _evidence_bundle_sha256(
        artifact=artifact,
        grid=grid,
        lineage=lineage,
        permissions=permissions,
        classification=classification,
        purpose=purpose,
    )
    if value["evidence_bundle_sha256"] != expected_evidence:
        raise QualifiedReferenceReleaseError("Evidence-bundle hash mismatch.")

    if status == SYNTHETIC_STATUS:
        if (
            value["dataset_mode"] != "fixture_demo"
            or value["confidence_class"] != "low"
            or value["processing_allowed"] is not False
            or value["eligible_for_controlled_model_development"] is not False
            or value["eligible_for_controlled_model_evaluation"] is not False
            or value["synthetic_fixture_processing_allowed"] is not True
            or lineage["assessment_status"] != "not_applicable_synthetic_fixture"
            or any(
                lineage[field] is not None
                for field in (
                    "acquisition_manifest_sha256",
                    "acquisition_manifest_file_sha256",
                    "acquisition_authority_receipt_sha256",
                    "authority_signing_key_id",
                    "authority_issued_at_utc",
                    "authority_expires_at_utc",
                    "external_authority_decision_sha256",
                    "external_authority_signing_key_id",
                    "reference_authorization_sha256",
                    "reference_product_id",
                    "reference_source_name",
                    "reference_source_timestamp",
                    "reference_observation_start",
                    "reference_observation_end",
                    "reference_permissions_sha256",
                    *_reference_authority_lineage_fields(),
                )
            )
            or any(lineage["sha256_by_role"].values())
            or blockers != (SYNTHETIC_LIMITATION,)
            or not all(permissions.values())
            or any(item["status"] != PURPOSE_SYNTHETIC for item in purposes)
            or classification["reference_authority_class"] != "synthetic_fixture"
            or classification["qualification_status"] != "synthetic_fixture_only"
        ):
            raise QualifiedReferenceReleaseError(
                "Synthetic release semantics are inconsistent or overclaimed."
            )
        _require_purpose_evidence(purposes, expected_evidence)
        return

    expected_development, expected_evaluation = _purpose_eligibility(purpose)
    if (
        value["dataset_mode"] != "candidate"
        or value["confidence_class"] not in {"medium", "high"}
        or value["processing_allowed"] is not True
        or value["eligible_for_controlled_model_development"]
        is not expected_development
        or value["eligible_for_controlled_model_evaluation"] is not expected_evaluation
        or value["synthetic_fixture_processing_allowed"] is not False
        or lineage["assessment_status"] != "ready"
        or lineage["assessment_blockers"]
        or blockers
        or classification["reference_authority_class"]
        not in QUALIFIED_AUTHORITY_CLASSES
        or classification["qualification_status"] != "qualified_expert_or_adjudicated"
        or classification["rights_evidence_status"]
        != "externally_verified_product_specific"
        or classification["independence_status"] != "independent_of_model_inputs"
        or any(
            lineage[field] is None
            for field in (
                "acquisition_manifest_sha256",
                "acquisition_manifest_file_sha256",
                "acquisition_authority_receipt_sha256",
                "authority_signing_key_id",
                "authority_issued_at_utc",
                "authority_expires_at_utc",
                "external_authority_decision_sha256",
                "external_authority_signing_key_id",
                "reference_authorization_sha256",
                "reference_product_id",
                "reference_source_name",
                "reference_source_timestamp",
                "reference_observation_start",
                "reference_observation_end",
                "reference_permissions_sha256",
                *_reference_authority_lineage_fields(),
            )
        )
        or any(
            lineage["sha256_by_role"][role] is None
            for role in ("pre_event_sar", "post_event_sar", "reference_mask")
        )
        or artifact["sha256"] != lineage["sha256_by_role"]["reference_mask"]
        or artifact["product_id"] != lineage["reference_product_id"]
        or value["source_name"] != lineage["reference_source_name"]
        or _format_utc(_timestamp(value["source_timestamp"], "source_timestamp"))
        != lineage["reference_source_timestamp"]
        or artifact["observation_start"] != lineage["reference_observation_start"]
        or artifact["observation_end"] != lineage["reference_observation_end"]
        or _canonical_sha256(permissions) != lineage["reference_permissions_sha256"]
        or lineage["reference_authority_purpose"] != purpose
        or lineage["reference_authority_class"]
        != classification["reference_authority_class"]
        or any(
            permissions[field] is not True
            for field in set(EXTERNAL_PERMISSION_FIELDS) - {"source_redistribution"}
        )
        or any(item["status"] != PURPOSE_QUALIFIED for item in purposes)
    ):
        raise QualifiedReferenceReleaseError(
            "Qualified release lacks ready signed authority or required scope."
        )
    issued = _timestamp(lineage["authority_issued_at_utc"], "authority issued_at")
    expires = _timestamp(
        lineage["authority_expires_at_utc"],
        "authority expires_at",
    )
    if not issued <= generated_at <= expires:
        raise QualifiedReferenceReleaseError(
            "Qualified release is outside authority validity."
        )
    reference_authority_issued = _timestamp(
        lineage["reference_authority_issued_at_utc"],
        "Reference Authority issued_at",
    )
    reference_authority_expires = _timestamp(
        lineage["reference_authority_expires_at_utc"],
        "Reference Authority expires_at",
    )
    if not reference_authority_issued <= generated_at <= reference_authority_expires:
        raise QualifiedReferenceReleaseError(
            "Qualified release is outside Reference Authority validity."
        )
    _require_purpose_evidence(purposes, expected_evidence)


def _validate_classification(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise QualifiedReferenceReleaseError(
            "evidence_classification must be an object."
        )
    _exact_keys(value, _CLASSIFICATION_KEYS, "evidence_classification")
    normalized = {key: _text(value[key], key) for key in _CLASSIFICATION_KEYS}
    _choice(
        normalized["reference_authority_class"],
        REFERENCE_AUTHORITY_CLASSES,
        "reference_authority_class",
    )
    return normalized


def _validate_permissions(value: Any) -> dict[str, bool]:
    if not isinstance(value, Mapping):
        raise QualifiedReferenceReleaseError("source_permissions must be an object.")
    if set(value) != set(EXTERNAL_PERMISSION_FIELDS):
        raise QualifiedReferenceReleaseError(
            "source_permissions must contain the exact controlled permission set."
        )
    normalized: dict[str, bool] = {}
    for field in EXTERNAL_PERMISSION_FIELDS:
        raw = value[field]
        if not isinstance(raw, bool):
            raise QualifiedReferenceReleaseError(
                f"source_permissions.{field} must be boolean."
            )
        normalized[field] = raw
    return normalized


def _validate_purposes(
    value: Any,
    *,
    selected_purpose: str,
) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list) or len(value) != 1:
        raise QualifiedReferenceReleaseError(
            "purpose_authorizations must contain exactly one purpose row."
        )
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, Mapping):
            raise QualifiedReferenceReleaseError(
                "Each purpose authorization must be an object."
            )
        _exact_keys(raw, _PURPOSE_KEYS, "purpose authorization")
        purpose = _choice(raw["purpose"], frozenset(PURPOSES), "purpose")
        if purpose in seen:
            raise QualifiedReferenceReleaseError(
                f"Duplicate purpose authorization: {purpose}."
            )
        seen.add(purpose)
        status = _choice(
            raw["status"],
            frozenset({PURPOSE_BLOCKED, PURPOSE_SYNTHETIC, PURPOSE_QUALIFIED}),
            "purpose status",
        )
        evidence = raw["evidence_sha256"]
        if evidence is not None:
            evidence = _sha256(evidence, "purpose evidence_sha256")
        normalized.append(
            {
                "purpose": purpose,
                "status": status,
                "authority_basis": _text(
                    raw["authority_basis"],
                    "purpose authority_basis",
                ),
                "evidence_sha256": evidence,
            }
        )
    if normalized[0]["purpose"] != selected_purpose:
        raise QualifiedReferenceReleaseError(
            "Purpose authorization differs from the selected receipt purpose."
        )
    return tuple(normalized)


def _validate_lineage(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise QualifiedReferenceReleaseError("acquisition_lineage must be an object.")
    _exact_keys(value, _LINEAGE_KEYS, "acquisition_lineage")
    status = _choice(
        value["assessment_status"],
        frozenset({"ready", "blocked", "not_applicable_synthetic_fixture"}),
        "assessment_status",
    )
    normalized = dict(value)
    normalized["assessment_status"] = status
    for field in (
        "acquisition_manifest_sha256",
        "acquisition_manifest_file_sha256",
        "acquisition_authority_receipt_sha256",
        "external_authority_decision_sha256",
        "reference_authorization_sha256",
        "reference_permissions_sha256",
        "reference_authority_decision_sha256",
        "reference_authority_decision_file_sha256",
        "reference_authority_signature_sha256",
        "reference_authority_signature_file_sha256",
        "reference_authority_public_key_sha256",
        "reference_authority_receipt_sha256",
    ):
        if normalized[field] is not None:
            normalized[field] = _sha256(normalized[field], field)
    for field in (
        "authority_signing_key_id",
        "external_authority_signing_key_id",
        "reference_product_id",
        "reference_authority_decision_id",
        "reference_authority_signing_key_id",
    ):
        if normalized[field] is not None:
            normalized[field] = _identifier(normalized[field], field)
    if normalized["reference_source_name"] is not None:
        normalized["reference_source_name"] = _text(
            normalized["reference_source_name"],
            "reference_source_name",
        )
    for field in (
        "reference_authority_id",
        "reference_authority_purpose",
        "reference_authority_class",
    ):
        if normalized[field] is not None:
            normalized[field] = _text(normalized[field], field)
    if normalized["reference_authority_purpose"] is not None:
        _choice(
            normalized["reference_authority_purpose"],
            frozenset(PURPOSES),
            "reference_authority_purpose",
        )
    if normalized["reference_authority_class"] is not None:
        _choice(
            normalized["reference_authority_class"],
            QUALIFIED_AUTHORITY_CLASSES,
            "reference_authority_class",
        )
    for field in (
        "authority_issued_at_utc",
        "authority_expires_at_utc",
        "reference_source_timestamp",
        "reference_observation_start",
        "reference_observation_end",
        "reference_authority_issued_at_utc",
        "reference_authority_expires_at_utc",
    ):
        if normalized[field] is not None:
            normalized[field] = _format_utc(_timestamp(normalized[field], field))
    scientific_fields = _reference_authority_lineage_fields()
    scientific_values = [normalized[field] for field in scientific_fields]
    if any(item is None for item in scientific_values):
        if any(item is not None for item in scientific_values):
            raise QualifiedReferenceReleaseError(
                "Reference Authority lineage must be wholly present or wholly absent."
            )
    else:
        receipt = {
            field: normalized[field]
            for field in scientific_fields
            if field != "reference_authority_receipt_sha256"
        }
        if normalized["reference_authority_receipt_sha256"] != _canonical_sha256(
            receipt
        ):
            raise QualifiedReferenceReleaseError(
                "Reference Authority receipt self-hash mismatch."
            )
    hashes = normalized["sha256_by_role"]
    if not isinstance(hashes, Mapping) or set(hashes) != {
        "pre_event_sar",
        "post_event_sar",
        "reference_mask",
    }:
        raise QualifiedReferenceReleaseError(
            "sha256_by_role must contain the exact acquisition roles."
        )
    normalized_hashes: dict[str, str | None] = {}
    for role, digest in hashes.items():
        normalized_hashes[role] = (
            None if digest is None else _sha256(digest, f"{role} sha256")
        )
    normalized["sha256_by_role"] = normalized_hashes
    normalized["assessment_blockers"] = list(
        _string_list(
            normalized["assessment_blockers"],
            "assessment_blockers",
            allow_empty=True,
        )
    )
    return normalized


def _validate_artifact_record(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise QualifiedReferenceReleaseError("reference_artifact must be an object.")
    _exact_keys(value, _ARTIFACT_KEYS, "reference_artifact")
    artifact = dict(value)
    _identifier(artifact["product_id"], "reference product_id")
    _safe_base_name(artifact["file_name"], "reference file_name")
    _sha256(artifact["sha256"], "reference sha256")
    if artifact["media_type"] != "image/tiff; application=geotiff":
        raise QualifiedReferenceReleaseError("Reference media_type is invalid.")
    artifact["crs"] = _epsg(artifact["crs"], "reference crs")
    artifact["transform"] = list(
        _transform(artifact["transform"], "reference transform")
    )
    artifact["width"] = _positive_integer(artifact["width"], "reference width")
    artifact["height"] = _positive_integer(artifact["height"], "reference height")
    if artifact["band_count"] != 1:
        raise QualifiedReferenceReleaseError("Reference band_count must be 1.")
    _text(artifact["dtype"], "reference dtype")
    nodata = _finite_number(artifact["nodata"], "reference nodata")
    if nodata in {0.0, 1.0}:
        raise QualifiedReferenceReleaseError(
            "Reference nodata conflicts with binary classes."
        )
    if artifact["valid_values"] != [0, 1]:
        raise QualifiedReferenceReleaseError(
            "Reference valid_values must be exactly [0, 1]."
        )
    if (
        artifact["covers_analysis_grid"] is not True
        or artifact["reprojection_performed"] is not False
    ):
        raise QualifiedReferenceReleaseError(
            "Reference must exactly cover the grid without reprojection."
        )
    artifact["observation_start"] = _format_utc(
        _timestamp(artifact["observation_start"], "observation_start")
    )
    artifact["observation_end"] = _format_utc(
        _timestamp(artifact["observation_end"], "observation_end")
    )
    return artifact


def _validate_grid_record(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise QualifiedReferenceReleaseError("analysis_grid must be an object.")
    _exact_keys(value, _GRID_KEYS, "analysis_grid")
    grid = dict(value)
    _safe_base_name(grid["file_name"], "analysis grid file_name")
    _sha256(grid["sha256"], "analysis grid sha256")
    grid["crs"] = _epsg(grid["crs"], "analysis grid crs")
    _validate_equal_area_crs(grid["crs"])
    grid["transform"] = list(_transform(grid["transform"], "analysis grid transform"))
    grid["width"] = _positive_integer(grid["width"], "analysis grid width")
    grid["height"] = _positive_integer(grid["height"], "analysis grid height")
    if (
        not isinstance(grid["cell_size"], list)
        or len(grid["cell_size"]) != 2
        or any(_finite_number(item, "cell_size") <= 0 for item in grid["cell_size"])
    ):
        raise QualifiedReferenceReleaseError(
            "analysis_grid.cell_size must contain two positive values."
        )
    return grid


def _validate_artifact_grid_compatibility(
    artifact: Mapping[str, Any],
    grid: Mapping[str, Any],
    *,
    source_timestamp: datetime,
) -> None:
    for field in ("crs", "transform", "width", "height"):
        if artifact[field] != grid[field]:
            raise QualifiedReferenceReleaseError(
                f"Reference artifact and analysis grid differ on {field}."
            )
    start = _timestamp(artifact["observation_start"], "observation_start")
    end = _timestamp(artifact["observation_end"], "observation_end")
    if end < start or not start <= source_timestamp <= end:
        raise QualifiedReferenceReleaseError(
            "Reference observation interval does not contain source_timestamp."
        )


def _evidence_bundle_sha256(
    *,
    artifact: Mapping[str, Any],
    grid: Mapping[str, Any],
    lineage: Mapping[str, Any],
    permissions: Mapping[str, bool],
    classification: Mapping[str, str],
    purpose: str,
) -> str:
    return _canonical_sha256(
        {
            "reference_artifact": dict(artifact),
            "analysis_grid": dict(grid),
            "acquisition_lineage": dict(lineage),
            "source_permissions": dict(permissions),
            "evidence_classification": dict(classification),
            "purpose": purpose,
        }
    )


def _require_purpose_evidence(
    purposes: Sequence[Mapping[str, Any]],
    expected_sha256: str,
) -> None:
    if any(item["evidence_sha256"] != expected_sha256 for item in purposes):
        raise QualifiedReferenceReleaseError(
            "Purpose authorization evidence does not bind the release bundle."
        )


def _require_acquisition(value: Any) -> AcquisitionGateAssessment:
    if not isinstance(value, AcquisitionGateAssessment):
        raise QualifiedReferenceReleaseError(
            "Acquisition evidence must come from assess_acquisition_manifest."
        )
    try:
        value.to_dict()
    except Exception as exc:
        raise QualifiedReferenceReleaseError(
            "Acquisition assessment is not a verified controlled-experiment object."
        ) from exc
    return value


def _reject_status_only_inputs(
    *,
    status: str,
    reference_artifact_path: str | Path | None,
    analysis_grid_contract_path: str | Path | None,
    acquisition_authority_receipt_path: str | Path | None,
    reference_authority_decision_path: str | Path | None,
    reference_authority_signature_path: str | Path | None,
    reference_authority_public_keys: Mapping[str, bytes] | None,
    observation_start: str | datetime | None,
    observation_end: str | datetime | None,
    reference_product_id: str | None,
) -> None:
    supplied = {
        "reference_artifact_path": reference_artifact_path,
        "analysis_grid_contract_path": analysis_grid_contract_path,
        "acquisition_authority_receipt_path": acquisition_authority_receipt_path,
        "reference_authority_decision_path": reference_authority_decision_path,
        "reference_authority_signature_path": reference_authority_signature_path,
        "reference_authority_public_keys": reference_authority_public_keys,
        "observation_start": observation_start,
        "observation_end": observation_end,
        "reference_product_id": reference_product_id,
    }
    present = sorted(key for key, value in supplied.items() if value is not None)
    if present:
        raise QualifiedReferenceReleaseError(
            f"{status} projection must not carry unverified evidence inputs: {present}."
        )


def _validate_equal_area_crs(value: str) -> None:
    try:
        from pyproj import CRS
    except ImportError as exc:  # pragma: no cover - minimal installation
        raise QualifiedReferenceReleaseError(
            "Equal-area validation requires PyProj."
        ) from exc
    try:
        crs = CRS.from_user_input(value)
    except Exception as exc:
        raise QualifiedReferenceReleaseError("Analysis CRS is invalid.") from exc
    operation = crs.coordinate_operation
    method = "" if operation is None else str(operation.method_name).lower()
    metre_axes = bool(crs.axis_info) and all(
        math.isclose(float(axis.unit_conversion_factor or 0.0), 1.0, abs_tol=1e-12)
        for axis in crs.axis_info
    )
    if not crs.is_projected or not metre_axes or "equal area" not in method:
        raise QualifiedReferenceReleaseError(
            "Analysis CRS must be projected, metre-based, and equal-area."
        )


def _stable_file_bytes(path: Path, label: str) -> bytes:
    if not path.is_file():
        raise QualifiedReferenceReleaseError(f"{label.capitalize()} is missing.")
    before = path.stat()
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise QualifiedReferenceReleaseError(f"Cannot read {label}: {exc}") from exc
    after = path.stat()
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or len(content) != after.st_size
    ):
        raise QualifiedReferenceReleaseError(
            f"{label.capitalize()} changed during verification."
        )
    return content


def _stable_file_sha256(path: Path, label: str) -> str:
    if not path.is_file():
        raise QualifiedReferenceReleaseError(f"{label.capitalize()} is missing.")
    before = path.stat()
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise QualifiedReferenceReleaseError(f"Cannot read {label}: {exc}") from exc
    after = path.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise QualifiedReferenceReleaseError(
            f"{label.capitalize()} changed during verification."
        )
    return digest.hexdigest()


def _require_unchanged_evidence_file(
    path: str | Path | None,
    expected_sha256: str | None,
    label: str,
) -> None:
    """Re-hash evidence immediately before sealing to detect path drift."""

    if path is None or expected_sha256 is None:
        raise QualifiedReferenceReleaseError(
            f"{label.capitalize()} lost its verified checksum binding."
        )
    current_sha256 = _stable_file_sha256(Path(path), label)
    if current_sha256 != expected_sha256:
        raise QualifiedReferenceReleaseError(
            f"{label.capitalize()} changed after verification and before sealing."
        )


def _reject_private_paths(value: Any, *, field: str = "release") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_private_paths(item, field=f"{field}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_private_paths(item, field=f"{field}[{index}]")
        return
    if isinstance(value, str) and _PRIVATE_PATH_RE.search(value):
        raise QualifiedReferenceReleaseError(
            f"{field} contains a private absolute path."
        )


def _exact_keys(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    if set(value) != set(expected):
        missing = sorted(set(expected) - set(value))
        extra = sorted(set(value) - set(expected))
        raise QualifiedReferenceReleaseError(
            f"{label} fields differ; missing={missing}, extra={extra}."
        )


def _identifier(value: Any, field: str) -> str:
    text = _text(value, field)
    if _SAFE_ID_RE.fullmatch(text) is None:
        raise QualifiedReferenceReleaseError(f"{field} is not a safe identifier.")
    return text


def _commit(value: Any) -> str:
    text = _text(value, "git_commit")
    if _COMMIT_RE.fullmatch(text) is None:
        raise QualifiedReferenceReleaseError(
            "git_commit must contain the full 40-character hex commit."
        )
    return text


def _sha256(value: Any, field: str) -> str:
    text = _text(value, field).lower()
    if _SHA256_RE.fullmatch(text) is None:
        raise QualifiedReferenceReleaseError(f"{field} is not a SHA-256 digest.")
    return text


def _epsg(value: Any, field: str) -> str:
    text = _text(value, field).upper()
    if _EPSG_RE.fullmatch(text) is None:
        raise QualifiedReferenceReleaseError(f"{field} must be an EPSG identifier.")
    return text


def _choice(value: Any, choices: frozenset[str], field: str) -> str:
    text = _text(value, field)
    if text not in choices:
        raise QualifiedReferenceReleaseError(
            f"{field} must be one of {sorted(choices)}."
        )
    return text


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QualifiedReferenceReleaseError(f"{field} must be a non-empty string.")
    return value.strip()


def _safe_base_name(value: Any, field: str) -> str:
    text = _text(value, field)
    if (
        text in {".", ".."}
        or "/" in text
        or "\\" in text
        or _PRIVATE_PATH_RE.search(text)
    ):
        raise QualifiedReferenceReleaseError(f"{field} must be a safe base name.")
    return text


def _timestamp(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise QualifiedReferenceReleaseError(
                f"{field} must be an ISO-8601 timestamp."
            ) from exc
    else:
        raise QualifiedReferenceReleaseError(
            f"{field} must be a timezone-aware timestamp."
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise QualifiedReferenceReleaseError(f"{field} must include a timezone.")
    return parsed.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _assumptions(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise QualifiedReferenceReleaseError("assumptions must be a string array.")
    items = tuple(_text(item, "assumption") for item in value)
    if not items or len(set(items)) != len(items):
        raise QualifiedReferenceReleaseError(
            "assumptions must be non-empty and unique."
        )
    return items


def _string_list(
    value: Any,
    field: str,
    *,
    allow_empty: bool,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise QualifiedReferenceReleaseError(f"{field} must be an array.")
    items = tuple(_text(item, field) for item in value)
    if not allow_empty and not items:
        raise QualifiedReferenceReleaseError(f"{field} must not be empty.")
    if len(set(items)) != len(items) or tuple(sorted(items)) != items:
        raise QualifiedReferenceReleaseError(
            f"{field} must be unique and deterministically sorted."
        )
    return items


def _transform(value: Any, field: str) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)) or len(value) != 6:
        raise QualifiedReferenceReleaseError(f"{field} must contain six numbers.")
    numbers = tuple(_finite_number(item, field) for item in value)
    if math.isclose(numbers[0], 0.0) or math.isclose(numbers[4], 0.0):
        raise QualifiedReferenceReleaseError(
            f"{field} must encode non-zero pixel dimensions."
        )
    return numbers


def _positive_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise QualifiedReferenceReleaseError(f"{field} must be a positive integer.")
    return value


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise QualifiedReferenceReleaseError(f"{field} must be numeric.")
    result = float(value)
    if not math.isfinite(result):
        raise QualifiedReferenceReleaseError(f"{field} must be finite.")
    return result


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
