from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from floodguard.label_factory.calibration import (
    ReviewerCalibrationReceipt,
    write_reviewer_calibration_receipt,
)
from floodguard.label_factory.human_roles import (
    HumanRolePackageError,
    IDENTITY_STATUS,
    LOCAL_EVIDENCE_STATUS,
    PACKAGE_SCHEMA,
    QUALIFICATION_STATUS,
    REQUEST_SCHEMA,
    ROLE_EVIDENCE_LIMITATION,
    build_human_role_package,
    validate_human_role_package,
)


UTC = timezone.utc
PROTOCOL = "label_factory_protocol_v1"
TAXONOMY = "flood_label_v1"
CREATED = "2024-09-17T00:00:00Z"
ACCEPTED = "2024-09-15T12:00:00Z"
CAPTURED = "2024-09-15T13:00:00Z"

ROLES = {
    "reference_authority": ("FG-RA-001", "FG-HUM-003"),
    "reviewer_a": ("FG-RV-A-001", "FG-HUM-001"),
    "reviewer_b": ("FG-RV-B-001", "FG-HUM-002"),
    "adjudicator_c": ("FG-ADJ-C-001", "FG-HUM-003"),
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resign_manifest(path: Path, mutate: object) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    payload.pop("manifest_sha256")
    payload["manifest_sha256"] = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _evidence_row(
    root: Path,
    *,
    number: int,
    evidence_type: str,
    role_id: str,
    person_id: str,
) -> dict[str, object]:
    evidence_id = f"FG-EV-{number:03d}"
    path = root / f"{evidence_id}.eml"
    path.write_text(
        f"Test-only attributable evidence for {role_id}, {person_id}, {evidence_type}.\n",
        encoding="utf-8",
    )
    return {
        "evidence_id": evidence_id,
        "evidence_type": evidence_type,
        "role_id": role_id,
        "person_id": person_id,
        "local_path": path.name,
        "sha256": _sha(path),
        "captured_at_utc": CAPTURED,
        "attributable_sender": f"sender-for-{person_id}",
        "attributable_recipient": "TeamBits project owner",
        "verification_status": LOCAL_EVIDENCE_STATUS,
    }


def _request(tmp_path: Path, *, operator_a: bool = True) -> tuple[dict[str, object], Path]:
    evidence_root = tmp_path / "source-evidence"
    evidence_root.mkdir()
    evidence: list[dict[str, object]] = []
    appointments: list[dict[str, object]] = []
    number = 1
    evidence_types = (
        ("acceptance_evidence_id", "role_acceptance"),
        ("conflict_evidence_id", "conflict_disclosure_and_decision"),
        ("data_terms_evidence_id", "participant_data_use_terms"),
        ("qualification_evidence_id", "qualification_basis"),
    )
    for category in (
        "reference_authority",
        "reviewer_a",
        "reviewer_b",
        "adjudicator_c",
    ):
        role_id, person_id = ROLES[category]
        refs: dict[str, str] = {}
        for field, evidence_type in evidence_types:
            row = _evidence_row(
                evidence_root,
                number=number,
                evidence_type=evidence_type,
                role_id=role_id,
                person_id=person_id,
            )
            evidence.append(row)
            refs[field] = str(row["evidence_id"])
            number += 1

        is_authority = category in {"reference_authority", "adjudicator_c"}
        is_operator_a = category == "reviewer_a" and operator_a
        conflict_declared = is_operator_a
        appointment: dict[str, object] = {
            "role_id": role_id,
            "role_category": category,
            "person_id": person_id,
            "appointment_status": "accepted_with_attributable_local_evidence",
            "accepted_at_utc": ACCEPTED,
            **refs,
            "conflict_declared": conflict_declared,
            "conflict_decision": (
                "managed_with_controls" if conflict_declared else "no_conflict_declared"
            ),
            "conflict_controls": (
                "Authority-controlled files and explicit non-independent reporting."
                if conflict_declared
                else "No conflict declared in the signed disclosure."
            ),
            "conflict_decided_by_person_id": "FG-HUM-001",
            "conflict_decided_at_utc": ACCEPTED,
            "data_terms_accepted_at_utc": ACCEPTED,
            "annotation_use_scope": "internal_research_only",
            "public_release_permission": False,
            "retention_end_utc": "2027-09-15T00:00:00Z",
            "withdrawal_terms": "Withdrawal is available before immutable release.",
            "compensation_basis": "paid_by_time",
            "qualification_summary": "Documented basis for accountable human assessment.",
            "project_operator": is_operator_a,
            "prior_prohibited_evidence_exposure": is_operator_a,
            "review_lane": (
                "authority_role_not_blinded"
                if is_authority
                else (
                    "authority_approved_mitigated_non_independent"
                    if is_operator_a
                    else "independent_blinded"
                )
            ),
            "independence_controls": (
                "Authority sees reference by role."
                if is_authority
                else (
                    "Operator A is reported as non-independent and isolated from B/reference."
                    if is_operator_a
                    else "Separate blinded delivery and return folders."
                )
            ),
            "independence_approved_by_role_id": None,
            "independence_decision_evidence_id": None,
        }
        appointments.append(appointment)

    if operator_a:
        ra_role, ra_person = ROLES["reference_authority"]
        approval = _evidence_row(
            evidence_root,
            number=number,
            evidence_type="independence_mitigation_approval",
            role_id=ra_role,
            person_id=ra_person,
        )
        evidence.append(approval)
        a = next(row for row in appointments if row["role_category"] == "reviewer_a")
        a["independence_approved_by_role_id"] = ra_role
        a["independence_decision_evidence_id"] = approval["evidence_id"]

    request: dict[str, object] = {
        "schema": REQUEST_SCHEMA,
        "package_name": "mae_sai_human_roles",
        "version": 1,
        "event_id": "TH-MAESAI-2024-09",
        "protocol_version": PROTOCOL,
        "taxonomy_version": TAXONOMY,
        "created_at_utc": CREATED,
        "created_by_person_id": "FG-HUM-001",
        "participation_mode": "paid_by_time",
        "annotation_use_scope": "internal_research_only",
        "public_release_requires_separate_project_decision": True,
        "reference_authority_adjudicator_dual_role_allowed": True,
        "candidate_research": [
            {
                "candidate_id": "FG-CAND-B-001",
                "display_name": "Public Reviewer B candidate only",
                "source_reference": "Local snapshot of a public institutional profile.",
                "researched_at_utc": "2024-09-14T00:00:00Z",
                "candidate_role_categories": ["reviewer_b"],
                "research_status": "public_research_only_not_nominated_or_accepted",
            },
            {
                "candidate_id": "FG-CAND-RA-001",
                "display_name": "Public Reference Authority candidate only",
                "source_reference": "Local snapshot of a public institutional profile.",
                "researched_at_utc": "2024-09-14T00:00:00Z",
                "candidate_role_categories": ["reference_authority", "adjudicator_c"],
                "research_status": "public_research_only_not_nominated_or_accepted",
            },
        ],
        "appointments": appointments,
        "evidence": evidence,
        "formal_review_authorization_requested": False,
        "calibration_receipt_file_sha256": None,
        "assumptions": "Test-only evidence package; no real person is appointed.",
    }
    return request, evidence_root


def _passing_receipt(
    path: Path,
    *,
    reviewers: tuple[str, str] = ("FG-RV-A-001", "FG-RV-B-001"),
) -> Path:
    query_ids = tuple(f"CAL-Q{index:02d}" for index in range(1, 9))
    annotations_by_reviewer = tuple(
        (
            reviewer,
            tuple(f"ANN-{reviewer}-{query_id}" for query_id in query_ids),
        )
        for reviewer in reviewers
    )
    annotation_ids = [
        annotation_id
        for _reviewer, ids in annotations_by_reviewer
        for annotation_id in ids
    ]
    per_query = [
        {
            "query_region_id": query_id,
            "comparable_cell_count": 4,
            "temporary_flood_dice": 1.0,
            "temporary_flood_iou": 1.0,
            "cohen_kappa": 1.0,
            "boundary_f1": 1.0,
        }
        for query_id in query_ids
    ]
    metrics = {
        "temporary_flood_dice": 1.0,
        "temporary_flood_iou": 1.0,
        "cohen_kappa": 1.0,
        "mean_boundary_f1": 1.0,
        "critical_strata_dice": {"urban_flood": 1.0},
        "query_count": 8,
        "comparable_cell_count": 32,
        "ignored_cell_count": 0,
        "per_query": per_query,
    }
    values = {
        "reviewer_ids": reviewers,
        "protocol_version": PROTOCOL,
        "taxonomy_version": TAXONOMY,
        "calibration_completed_at_utc": datetime(2024, 9, 16, 0, 0, tzinfo=UTC),
        "formal_review_not_before_utc": datetime(2024, 9, 16, 0, 30, tzinfo=UTC),
        "query_manifest_sha256": "0" * 64,
        "query_region_ids": query_ids,
        "annotation_sha256_by_id": tuple(
            (annotation_id, hashlib.sha256(annotation_id.encode()).hexdigest())
            for annotation_id in annotation_ids
        ),
        "annotation_ids_by_reviewer": annotations_by_reviewer,
        "reviewer_cell_sha256_by_reviewer": tuple(
            (reviewer, str(index) * 64)
            for index, reviewer in enumerate(reviewers, start=1)
        ),
        "reviewer_cell_manifest_sha256_by_reviewer": tuple(
            (reviewer, str(index) * 64)
            for index, reviewer in enumerate(reviewers, start=3)
        ),
        "calibration_reference_manifest_sha256": "5" * 64,
        "calibration_reference_cells_sha256": "6" * 64,
        "grid_contract_sha256_by_query": tuple((query_id, "7" * 64) for query_id in query_ids),
        "source_registry_sha256_by_query": tuple((query_id, "8" * 64) for query_id in query_ids),
        "source_timestamp_by_query": tuple((query_id, "2024-09-15T23:00:00Z") for query_id in query_ids),
        "metrics_by_reviewer": tuple((reviewer, metrics) for reviewer in reviewers),
        "thresholds": (
            ("cohen_kappa", 0.75),
            ("critical_stratum_dice", 0.65),
            ("mean_boundary_f1", 0.70),
            ("temporary_flood_dice", 0.75),
        ),
        "query_strata_sha256": "9" * 64,
        "assumptions": "Synthetic passing receipt for human-role contract tests.",
    }
    provisional = ReviewerCalibrationReceipt(**values, receipt_sha256="")
    digest = hashlib.sha256(
        json.dumps(
            provisional.to_dict(include_self_hash=False),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    receipt = ReviewerCalibrationReceipt(**values, receipt_sha256=digest)
    write_reviewer_calibration_receipt(receipt, path)
    return path


def test_precalibration_package_is_immutable_hold_and_candidate_is_not_appointment(
    tmp_path: Path,
) -> None:
    request, evidence_root = _request(tmp_path)
    output = tmp_path / "human-roles-v1"

    build_human_role_package(request, evidence_root=evidence_root, output_dir=output)
    manifest = validate_human_role_package(output)

    assert manifest["artifact_schema"] == PACKAGE_SCHEMA
    assert manifest["formal_review_authorized"] is False
    assert manifest["formal_review_authorized_from_utc"] is None
    assert manifest["genuinely_blinded_double_review"] is False
    assert manifest["candidate_research"][0]["confers_nomination"] is False
    assert manifest["candidate_research"][0]["confers_acceptance"] is False
    assert {row["candidate_id"] for row in manifest["candidate_research"]} == {
        "FG-CAND-B-001",
        "FG-CAND-RA-001",
    }
    assert manifest["identity_verification_status"] == IDENTITY_STATUS
    assert manifest["qualification_verification_status"] == QUALIFICATION_STATUS
    assert manifest["role_evidence_limitation"] == ROLE_EVIDENCE_LIMITATION
    assert manifest["eligible_for_model_training"] is False
    assert manifest["eligible_for_decision_layer"] is False
    with pytest.raises(HumanRolePackageError, match="cannot be overwritten"):
        build_human_role_package(request, evidence_root=evidence_root, output_dir=output)


def test_two_external_unexposed_reviewers_are_genuinely_blinded(tmp_path: Path) -> None:
    request, evidence_root = _request(tmp_path, operator_a=False)
    output = tmp_path / "human-roles-external"
    build_human_role_package(request, evidence_root=evidence_root, output_dir=output)

    assert validate_human_role_package(output)["genuinely_blinded_double_review"] is True


def test_operator_a_cannot_be_silently_marked_independent(tmp_path: Path) -> None:
    request, evidence_root = _request(tmp_path)
    a = next(row for row in request["appointments"] if row["role_category"] == "reviewer_a")
    a["review_lane"] = "independent_blinded"
    a["independence_approved_by_role_id"] = None
    a["independence_decision_evidence_id"] = None

    with pytest.raises(HumanRolePackageError, match="cannot be represented as independently blinded"):
        build_human_role_package(
            request,
            evidence_root=evidence_root,
            output_dir=tmp_path / "unsafe-operator-a",
        )


def test_reviewer_b_must_remain_independent_and_nonoperator(tmp_path: Path) -> None:
    request, evidence_root = _request(tmp_path)
    b = next(row for row in request["appointments"] if row["role_category"] == "reviewer_b")
    b["project_operator"] = True

    with pytest.raises(HumanRolePackageError, match="Reviewer B must be"):
        build_human_role_package(
            request,
            evidence_root=evidence_root,
            output_dir=tmp_path / "unsafe-b",
        )


def test_same_person_for_a_and_b_is_rejected(tmp_path: Path) -> None:
    request, evidence_root = _request(tmp_path, operator_a=False)
    b = next(row for row in request["appointments"] if row["role_category"] == "reviewer_b")
    b["person_id"] = "FG-HUM-001"
    for row in request["evidence"]:
        if row["role_id"] == "FG-RV-B-001":
            row["person_id"] = "FG-HUM-001"

    with pytest.raises(HumanRolePackageError, match="A and Reviewer B must be different"):
        build_human_role_package(
            request,
            evidence_root=evidence_root,
            output_dir=tmp_path / "same-reviewer",
        )


def test_ra_equals_c_requires_explicit_allowance(tmp_path: Path) -> None:
    request, evidence_root = _request(tmp_path)
    request["reference_authority_adjudicator_dual_role_allowed"] = False

    with pytest.raises(HumanRolePackageError, match="RA=C requires explicit"):
        build_human_role_package(
            request,
            evidence_root=evidence_root,
            output_dir=tmp_path / "undeclared-dual",
        )


@pytest.mark.parametrize("failure", ["missing", "hash"])
def test_local_evidence_must_exist_and_match_sha(tmp_path: Path, failure: str) -> None:
    request, evidence_root = _request(tmp_path)
    first = request["evidence"][0]
    if failure == "missing":
        (evidence_root / first["local_path"]).unlink()
        match = "does not exist"
    else:
        first["sha256"] = "f" * 64
        match = "mismatch"

    with pytest.raises(HumanRolePackageError, match=match):
        build_human_role_package(
            request,
            evidence_root=evidence_root,
            output_dir=tmp_path / "bad-evidence",
        )


def test_evidence_path_cannot_escape_root(tmp_path: Path) -> None:
    request, evidence_root = _request(tmp_path)
    request["evidence"][0]["local_path"] = "../outside.eml"

    with pytest.raises(HumanRolePackageError, match="safe relative"):
        build_human_role_package(
            request,
            evidence_root=evidence_root,
            output_dir=tmp_path / "escaped",
        )


def test_formal_review_request_without_receipt_fails_closed(tmp_path: Path) -> None:
    request, evidence_root = _request(tmp_path)
    request["formal_review_authorization_requested"] = True

    with pytest.raises(HumanRolePackageError, match="without an exact passing"):
        build_human_role_package(
            request,
            evidence_root=evidence_root,
            output_dir=tmp_path / "no-receipt",
        )


def test_exact_passing_receipt_opens_gate_for_exact_reviewers(tmp_path: Path) -> None:
    request, evidence_root = _request(tmp_path)
    receipt = _passing_receipt(tmp_path / "passing-receipt.json")
    request["formal_review_authorization_requested"] = True
    request["calibration_receipt_file_sha256"] = _sha(receipt)
    output = tmp_path / "authorized"

    build_human_role_package(
        request,
        evidence_root=evidence_root,
        output_dir=output,
        calibration_receipt_path=receipt,
    )
    manifest = validate_human_role_package(output)

    assert manifest["formal_review_authorized"] is True
    assert manifest["formal_review_authorized_from_utc"] == "2024-09-16T00:30:00Z"
    assert manifest["calibration_receipt"]["calibration_passed"] is True
    assert manifest["genuinely_blinded_double_review"] is False


def test_receipt_for_other_reviewer_ids_is_rejected(tmp_path: Path) -> None:
    request, evidence_root = _request(tmp_path)
    receipt = _passing_receipt(
        tmp_path / "wrong-reviewers.json",
        reviewers=("FG-RV-A-001", "FG-RV-B-999"),
    )
    request["formal_review_authorization_requested"] = True
    request["calibration_receipt_file_sha256"] = _sha(receipt)

    with pytest.raises(HumanRolePackageError, match="do not exactly match"):
        build_human_role_package(
            request,
            evidence_root=evidence_root,
            output_dir=tmp_path / "wrong-reviewers",
            calibration_receipt_path=receipt,
        )


def test_package_and_evidence_tamper_are_rejected(tmp_path: Path) -> None:
    request, evidence_root = _request(tmp_path)
    output = tmp_path / "tamper"
    build_human_role_package(request, evidence_root=evidence_root, output_dir=output)
    evidence_path = next((output / "evidence").iterdir())
    evidence_path.write_text("tampered", encoding="utf-8")

    with pytest.raises(HumanRolePackageError, match="failed checksum"):
        validate_human_role_package(output)

    # Restore by rebuilding another package and mutate the self-hashed manifest.
    output2 = tmp_path / "manifest-tamper"
    build_human_role_package(request, evidence_root=evidence_root, output_dir=output2)
    manifest_path = output2 / "human_role_package.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["formal_review_authorized"] = True
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(HumanRolePackageError, match="self-hash"):
        validate_human_role_package(output2)


def test_self_resigned_unsafe_semantics_are_still_rejected(tmp_path: Path) -> None:
    request, evidence_root = _request(tmp_path)
    output = tmp_path / "resigned-unsafe"
    build_human_role_package(request, evidence_root=evidence_root, output_dir=output)
    manifest_path = output / "human_role_package.json"

    def _misrepresent_operator(payload: dict[str, object]) -> None:
        appointments = payload["appointments"]
        a = next(row for row in appointments if row["role_category"] == "reviewer_a")
        a["review_lane"] = "independent_blinded"

    _resign_manifest(manifest_path, _misrepresent_operator)
    with pytest.raises(HumanRolePackageError, match="cannot be represented as independently blinded"):
        validate_human_role_package(output)

    output2 = tmp_path / "resigned-candidate"
    build_human_role_package(request, evidence_root=evidence_root, output_dir=output2)
    manifest_path2 = output2 / "human_role_package.json"

    def _promote_candidate(payload: dict[str, object]) -> None:
        payload["candidate_research"][0]["confers_nomination"] = True

    _resign_manifest(manifest_path2, _promote_candidate)
    with pytest.raises(HumanRolePackageError, match="must not confer nomination"):
        validate_human_role_package(output2)


def test_child_version_binds_parent_and_role_ids_cannot_be_reassigned(tmp_path: Path) -> None:
    request, evidence_root = _request(tmp_path)
    parent = tmp_path / "v1"
    build_human_role_package(request, evidence_root=evidence_root, output_dir=parent)
    child_request = deepcopy(request)
    child_request["version"] = 2
    child_request["created_at_utc"] = "2024-09-18T00:00:00Z"
    child = tmp_path / "v2"
    build_human_role_package(
        child_request,
        evidence_root=evidence_root,
        output_dir=child,
        parent_package=parent,
    )
    manifest = validate_human_role_package(child)
    assert manifest["parent_package_id"] == "mae_sai_human_roles_v1"
    assert manifest["parent_manifest_sha256"] == validate_human_role_package(parent)["manifest_sha256"]

    unsafe = deepcopy(child_request)
    unsafe["version"] = 3
    unsafe["created_at_utc"] = "2024-09-19T00:00:00Z"
    a = next(row for row in unsafe["appointments"] if row["role_category"] == "reviewer_a")
    a["person_id"] = "FG-HUM-099"
    for row in unsafe["evidence"]:
        if row["role_id"] == "FG-RV-A-001":
            row["person_id"] = "FG-HUM-099"
    with pytest.raises(HumanRolePackageError, match="cannot be reassigned"):
        build_human_role_package(
            unsafe,
            evidence_root=evidence_root,
            output_dir=tmp_path / "v3-unsafe",
            parent_package=child,
        )


def test_cli_build_and_validate_report_hold(tmp_path: Path) -> None:
    request, evidence_root = _request(tmp_path)
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")
    output = tmp_path / "cli-package"
    script = Path(__file__).resolve().parents[1] / "scripts" / "build_label_factory_human_roles.py"

    built = subprocess.run(
        [
            sys.executable,
            str(script),
            "build",
            "--request-json",
            str(request_path),
            "--evidence-root",
            str(evidence_root),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert built.returncode == 0, built.stderr
    assert "Formal review authorized: false" in built.stdout
    assert "Genuinely blinded double review: false" in built.stdout
    assert "training=false" in built.stdout

    validated = subprocess.run(
        [sys.executable, str(script), "validate", "--package", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert validated.returncode == 0, validated.stderr
    assert "Validated immutable human-role package" in validated.stdout
