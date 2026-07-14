from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from floodguard.label_factory.calibration_reserve import (
    build_calibration_reserve_design,
    load_calibration_reserve_design_receipt,
)
from floodguard.label_factory.human_roles import build_human_role_package
from floodguard.label_factory.reference_authority_approval import (
    APPROVED_STATUS,
    PACKAGE_SCHEMA,
    REQUEST_SCHEMA,
    ReferenceAuthorityApprovalError,
    build_reference_authority_approval_package,
    validate_reference_authority_approval_package,
)
from floodguard.label_factory.review_derivatives import (
    write_review_derivative_lineage_receipt,
)
from test_label_factory_calibration_reserve import (
    _canonical_sha256 as _reserve_json_sha,
    _fixture as _reserve_fixture,
)
from test_label_factory_human_roles import (
    _passing_receipt,
    _request as _human_request,
)
from test_label_factory_review_derivatives import _receipt as _derivative_receipt


EVENT_ID = "TH-MAESAI-2024-09"
DECISION_AT = "2026-07-11T13:00:00Z"
CAPTURED_AT = "2026-07-11T14:00:00Z"
CREATED_AT = "2026-07-11T15:00:00Z"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _role_package(root: Path, *, authorized: bool = False) -> Path:
    root.mkdir(parents=True)
    request, evidence_root = _human_request(root)
    request["event_id"] = EVENT_ID
    output = root / "human-roles"
    if authorized:
        receipt = _passing_receipt(root / "passing-calibration.json")
        request["formal_review_authorization_requested"] = True
        request["calibration_receipt_file_sha256"] = _sha(receipt)
        build_human_role_package(
            request,
            evidence_root=evidence_root,
            output_dir=output,
            calibration_receipt_path=receipt,
        )
    else:
        build_human_role_package(
            request,
            evidence_root=evidence_root,
            output_dir=output,
        )
    return output


def _design_package(root: Path) -> Path:
    grid, context = _reserve_fixture(root)
    _rewrite_fixture_event(grid, EVENT_ID)
    output = root / "reserve-design"
    build_calibration_reserve_design(
        canonical_grid_directory=grid,
        context_alignment_manifest_path=context,
        output_directory=output,
        design_id="mae_sai_reserve_design_v1",
        calibration_query_count=8,
        retest_query_count=8,
        reserve_tile_count=2,
        minimum_remaining_pool_queries=8,
        created_at_utc="2026-07-11T12:00:00Z",
    )
    return output


def _rewrite_fixture_event(grid: Path, event_id: str) -> None:
    for name in ("canonical_tiles.csv", "canonical_query_regions.csv"):
        path = grid / name
        frame = pd.read_csv(path)
        frame["event_id"] = event_id
        frame.to_csv(path, index=False)

    manifest_path = grid / "release_manifest.csv"
    manifest = pd.read_csv(manifest_path)
    for name in ("canonical_tiles.csv", "canonical_query_regions.csv"):
        path = grid / name
        mask = manifest["file_name"] == name
        manifest.loc[mask, "file_size_bytes"] = path.stat().st_size
        manifest.loc[mask, "sha256"] = _sha(path)
    manifest.to_csv(manifest_path, index=False)

    seal_path = grid / "release_seal.json"
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    seal["release_manifest_sha256"] = _sha(manifest_path)
    seal.pop("seal_sha256")
    seal["seal_sha256"] = _reserve_json_sha(seal)
    seal_path.write_text(
        json.dumps(seal, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def _decision_inputs(
    root: Path,
    design: Path,
    *,
    derivative_decision: str = "not_submitted",
    derivative_receipt: Path | None = None,
) -> tuple[dict[str, object], Path, Path]:
    evidence_root = root / "authority-evidence"
    evidence_root.mkdir(parents=True)
    evidence_path = evidence_root / "authority-decision.eml"
    evidence_path.write_text(
        "Synthetic attributable Reference Authority decision evidence.\n",
        encoding="utf-8",
    )
    procedure = root / "reference-procedure.md"
    procedure.write_text(
        "# Synthetic fixed reference procedure\n\nTest-only, no real labels.\n",
        encoding="utf-8",
    )
    design_receipt = load_calibration_reserve_design_receipt(
        design / "design_receipt.json"
    )
    candidate_id = design_receipt["provisional_recommendation"]["candidate_id"]
    derivative_sha = None
    if derivative_receipt is not None:
        derivative_sha = json.loads(
            derivative_receipt.read_text(encoding="utf-8")
        )["receipt_sha256"]
    request: dict[str, object] = {
        "schema": REQUEST_SCHEMA,
        "package_id": "mae_sai_reference_authority_decision_v1",
        "event_id": EVENT_ID,
        "created_at_utc": CREATED_AT,
        "reference_authority_role_id": "FG-RA-001",
        "reference_authority_person_id": "FG-HUM-003",
        "decision_evidence": {
            "evidence_id": "FG-RA-DEC-001",
            "evidence_type": "email_export",
            "local_path": evidence_path.name,
            "sha256": _sha(evidence_path),
            "decision_at_utc": DECISION_AT,
            "captured_at_utc": CAPTURED_AT,
            "attributable_sender": "Synthetic Reference Authority",
            "attributable_recipient": "TeamBits project owner",
            "attributable_sender_person_id": "FG-HUM-003",
        },
        "reserve_design_decision": {
            "design_id": design_receipt["design_id"],
            "chosen_candidate_id": candidate_id,
            "decision": "approved",
            "rationale": "Synthetic test accepts the static-context reserve tradeoff.",
        },
        "review_derivative_decision": {
            "decision": derivative_decision,
            "receipt_sha256": derivative_sha,
            "rationale": (
                "Synthetic test explicitly records whether the display was submitted."
            ),
        },
        "reference_procedure_decision": {
            "document_version": "reference_procedure_v1",
            "document_sha256": _sha(procedure),
            "decision": "approved",
            "rationale": "Synthetic test accepts the exact fixed procedure bytes.",
        },
        "authority_attestations": {
            "reserve_uses_static_non_label_context_only": True,
            "reserve_candidate_is_not_flood_truth": True,
            "calibration_and_retest_queries_remain_unselected_and_unseen": True,
            "reference_procedure_is_fixed_to_the_bound_hash_and_version": True,
            "derivative_decision_governs_display_inclusion_only": True,
            "no_bundle_calibration_or_formal_review_is_authorized": True,
            "human_role_evidence_limitation_is_acknowledged": True,
        },
        "assumptions": "Synthetic contract test only; no real human decision.",
    }
    return request, evidence_root, procedure


def _base_fixture(
    tmp_path: Path,
) -> tuple[Path, Path, dict[str, object], Path, Path]:
    roles = _role_package(tmp_path / "roles")
    design = _design_package(tmp_path / "design-inputs")
    request, evidence_root, procedure = _decision_inputs(tmp_path, design)
    return roles, design, request, evidence_root, procedure


def test_approved_package_only_opens_separate_construction_step(
    tmp_path: Path,
) -> None:
    roles, design, request, evidence_root, procedure = _base_fixture(tmp_path)
    output = tmp_path / "authority-package"

    build_reference_authority_approval_package(
        request,
        evidence_root=evidence_root,
        human_role_package=roles,
        calibration_reserve_design_package=design,
        reference_procedure_path=procedure,
        output_directory=output,
    )
    manifest = validate_reference_authority_approval_package(output)

    assert manifest["artifact_schema"] == PACKAGE_SCHEMA
    assert manifest["approval_status"] == APPROVED_STATUS
    scope = manifest["authorization_scope"]
    assert scope["may_start_separate_canonical_reserve_construction"] is True
    assert scope["may_start_separate_reference_construction"] is True
    assert scope["may_include_bound_review_derivatives_in_that_next_construction"] is False
    assert scope["calibration_query_selection"] is False
    assert scope["calibration_execution"] is False
    assert scope["review_bundle_construction"] is False
    assert scope["formal_review"] is False
    assert all(value is False for key, value in manifest["safety"].items() if not key.endswith("_ids"))
    assert manifest["safety"]["calibration_query_ids"] == []
    assert manifest["safety"]["retest_query_ids"] == []
    serialized = json.dumps(manifest)
    assert "T0_Q0" not in serialized
    assert manifest["reference_authority"]["appointment_status"] == (
        "accepted_with_attributable_local_evidence"
    )
    assert manifest["decision_evidence"]["semantic_verification_status"] == (
        "not_verified_from_opaque_evidence_by_software"
    )

    with pytest.raises(ReferenceAuthorityApprovalError, match="immutable"):
        build_reference_authority_approval_package(
            request,
            evidence_root=evidence_root,
            human_role_package=roles,
            calibration_reserve_design_package=design,
            reference_procedure_path=procedure,
            output_directory=output,
        )


@pytest.mark.parametrize("decision", ["approved", "rejected"])
def test_optional_derivative_requires_explicit_decision_and_exact_receipt(
    tmp_path: Path, decision: str
) -> None:
    roles = _role_package(tmp_path / "roles")
    design = _design_package(tmp_path / "design-inputs")
    _processing, _spec, derivative = _derivative_receipt(tmp_path / "derivative")
    derivative_path = write_review_derivative_lineage_receipt(
        derivative, tmp_path / "derivative-receipt.json"
    )
    request, evidence_root, procedure = _decision_inputs(
        tmp_path,
        design,
        derivative_decision=decision,
        derivative_receipt=derivative_path,
    )

    output = tmp_path / f"authority-{decision}"
    build_reference_authority_approval_package(
        request,
        evidence_root=evidence_root,
        human_role_package=roles,
        calibration_reserve_design_package=design,
        reference_procedure_path=procedure,
        review_derivative_lineage_receipt_path=derivative_path,
        output_directory=output,
    )
    manifest = validate_reference_authority_approval_package(output)
    derivative_binding = manifest["review_derivative_decision"]
    assert derivative_binding["decision"] == decision
    assert derivative_binding["receipt_sha256"] == derivative["receipt_sha256"]
    assert derivative_binding["display_inclusion_in_next_construction"] is (
        decision == "approved"
    )
    assert derivative_binding["authorizes_review_bundle"] is False
    assert manifest["authorization_scope"]["formal_review"] is False


def test_fails_closed_on_missing_derivative_or_wrong_evidence_hash(
    tmp_path: Path,
) -> None:
    roles, design, request, evidence_root, procedure = _base_fixture(tmp_path)
    request["review_derivative_decision"] = {
        "decision": "approved",
        "receipt_sha256": "a" * 64,
        "rationale": "A receipt is deliberately omitted from this failure case.",
    }
    with pytest.raises(ReferenceAuthorityApprovalError, match="requires the exact"):
        build_reference_authority_approval_package(
            request,
            evidence_root=evidence_root,
            human_role_package=roles,
            calibration_reserve_design_package=design,
            reference_procedure_path=procedure,
            output_directory=tmp_path / "missing-derivative",
        )

    changed = deepcopy(request)
    changed["review_derivative_decision"] = {
        "decision": "not_submitted",
        "receipt_sha256": None,
        "rationale": "No derivative is submitted in this failure case.",
    }
    changed["decision_evidence"]["sha256"] = "f" * 64
    with pytest.raises(ReferenceAuthorityApprovalError, match="bytes differ"):
        build_reference_authority_approval_package(
            changed,
            evidence_root=evidence_root,
            human_role_package=roles,
            calibration_reserve_design_package=design,
            reference_procedure_path=procedure,
            output_directory=tmp_path / "wrong-evidence",
        )


def test_rejects_wrong_authority_and_postcalibration_role_package(
    tmp_path: Path,
) -> None:
    roles, design, request, evidence_root, procedure = _base_fixture(tmp_path)
    wrong = deepcopy(request)
    wrong["reference_authority_person_id"] = "FG-HUM-999"
    with pytest.raises(ReferenceAuthorityApprovalError, match="appointed person"):
        build_reference_authority_approval_package(
            wrong,
            evidence_root=evidence_root,
            human_role_package=roles,
            calibration_reserve_design_package=design,
            reference_procedure_path=procedure,
            output_directory=tmp_path / "wrong-authority",
        )

    authorized_roles = _role_package(tmp_path / "authorized-roles", authorized=True)
    with pytest.raises(ReferenceAuthorityApprovalError, match="pre-calibration"):
        build_reference_authority_approval_package(
            request,
            evidence_root=evidence_root,
            human_role_package=authorized_roles,
            calibration_reserve_design_package=design,
            reference_procedure_path=procedure,
            output_directory=tmp_path / "postcalibration",
        )


def test_rejects_tampered_package_even_when_manifest_is_rehashed(
    tmp_path: Path,
) -> None:
    roles, design, request, evidence_root, procedure = _base_fixture(tmp_path)
    output = tmp_path / "authority-package"
    build_reference_authority_approval_package(
        request,
        evidence_root=evidence_root,
        human_role_package=roles,
        calibration_reserve_design_package=design,
        reference_procedure_path=procedure,
        output_directory=output,
    )
    evidence = output / "evidence" / "reference_authority_decision.eml"
    evidence.write_text("tampered", encoding="utf-8")
    with pytest.raises(ReferenceAuthorityApprovalError, match="size mismatch|checksum mismatch"):
        validate_reference_authority_approval_package(output)

    output2 = tmp_path / "resigned-unsafe"
    build_reference_authority_approval_package(
        request,
        evidence_root=evidence_root,
        human_role_package=roles,
        calibration_reserve_design_package=design,
        reference_procedure_path=procedure,
        output_directory=output2,
    )
    manifest_path = output2 / "reference_authority_approval.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["safety"]["formal_review_authorized"] = True
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    manifest["manifest_sha256"] = hashlib.sha256(
        json.dumps(
            unsigned,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ReferenceAuthorityApprovalError, match="unsafe enabled"):
        validate_reference_authority_approval_package(output2)


def test_cli_build_and_validate_keep_formal_review_closed(tmp_path: Path) -> None:
    roles, design, request, evidence_root, procedure = _base_fixture(tmp_path)
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")
    output = tmp_path / "cli-package"
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "build_reference_authority_approval.py"
    )
    built = subprocess.run(
        [
            sys.executable,
            str(script),
            "build",
            "--request-json",
            str(request_path),
            "--evidence-root",
            str(evidence_root),
            "--human-role-package",
            str(roles),
            "--calibration-reserve-design-package",
            str(design),
            "--reference-procedure",
            str(procedure),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert built.returncode == 0, built.stderr
    assert "Approval status: approved_next_construction_only" in built.stdout
    assert "formal-review=false" in built.stdout

    validated = subprocess.run(
        [sys.executable, str(script), "validate", "--package", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert validated.returncode == 0, validated.stderr
    assert "Validated immutable Reference Authority package" in validated.stdout
