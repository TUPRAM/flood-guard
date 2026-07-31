from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from floodguard.label_factory.rights_clearance import (
    COPDEM_ARTICLE_6C_NOTICE,
    COPDEM_MODIFIED_NOTICE,
    COPDEM_RAW_NOTICE,
    DECISION_SCHEMA,
    JRC_ATTRIBUTION,
    RightsClearanceError,
    RightsOwnerDecision,
    SENTINEL_MODIFIED_NOTICE,
    SENTINEL_RAW_NOTICE,
    TIMESTAMP_BASIS,
    WORLDCOVER_ATTRIBUTION,
    build_rights_clearance_package,
    validate_cleared_registry_binding,
    validate_rights_clearance_package,
)


DECLARED_TIME = "2026-07-11T03:40:00Z"
TECHNICAL_TIME = "2026-07-10T15:43:44Z"


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json_sha256(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def _resign_after_content_change(package: Path, artifact_name: str) -> None:
    manifest_path = package / "package_manifest.csv"
    fields: list[str]
    with manifest_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or ())
        rows = list(reader)
    artifact = package / artifact_name
    for row in rows:
        if row["file_name"] == artifact_name:
            row["file_size_bytes"] = str(artifact.stat().st_size)
            row["sha256"] = _sha256(artifact)
            break
    else:
        raise AssertionError(f"artifact not manifested: {artifact_name}")
    _write_csv(manifest_path, fields, rows)
    seal_path = package / "package_seal.json"
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    seal["package_manifest_sha256"] = _sha256(manifest_path)
    seal.pop("seal_sha256")
    seal["seal_sha256"] = _canonical_json_sha256(seal)
    seal_path.write_text(
        json.dumps(seal, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _decision() -> dict[str, object]:
    approval = {
        "local_processing": True,
        "ml_label_derivation": True,
        "blinded_reviewer_display": True,
        "redistribution_requested": True,
    }
    return {
        "schema": DECISION_SCHEMA,
        "owner_name": "I Putu Pramana Putra",
        "organization": "TeamBits",
        "decision_timestamp_utc": DECLARED_TIME,
        "sources": {
            "sentinel1": dict(approval),
            "jrc_global_surface_water": dict(approval),
            "esa_worldcover_2021": dict(approval),
            "copernicus_dem_glo30": dict(approval),
        },
    }


def _pending_package(root: Path) -> Path:
    root.mkdir()
    event_fields = [
        "event_id",
        "label_status",
        "source_rights_status",
        "processing_allowed",
        "ml_label_derivation_allowed",
        "validation_allowed",
        "source_timestamp",
        "assumptions",
    ]
    _write_csv(
        root / "events.csv",
        event_fields,
        [
            {
                "event_id": "TH-MAESAI-2024-09",
                "label_status": "unreviewed_human_roles_tbd",
                "source_rights_status": "review_pending",
                "processing_allowed": "false",
                "ml_label_derivation_allowed": "false",
                "validation_allowed": "false",
                "source_timestamp": TECHNICAL_TIME,
                "assumptions": (
                    "Technical processing exists but accountable rights and "
                    "reference approvals remain unsigned."
                ),
            }
        ],
    )
    asset_fields = [
        "asset_id",
        "license_status",
        "processing_allowed",
        "ml_label_derivation_allowed",
        "redistribution_status",
        "source_timestamp",
        "assumptions",
    ]
    _write_csv(
        root / "source_assets.csv",
        asset_fields,
        [
            {
                "asset_id": "mae_sai_pre_vv",
                "license_status": "review_pending",
                "processing_allowed": "false",
                "ml_label_derivation_allowed": "false",
                "redistribution_status": "not_assessed_no_redistribution",
                "source_timestamp": TECHNICAL_TIME,
                "assumptions": "Verified Sentinel source. Rights owner is TBD.",
            }
        ],
    )
    context_fields = [
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
    ]
    context_rows = [
        {
            "context_layer_id": "land_cover",
            "source_roles": "worldcover",
            "allowed_for_blinded_review_candidate": "true",
            "eligible_for_current_context_layers_csv": "true",
        },
        {
            "context_layer_id": "permanent_water_context",
            "source_roles": "jrc_occurrence+jrc_seasonality",
            "allowed_for_blinded_review_candidate": "true",
            "eligible_for_current_context_layers_csv": "true",
        },
        {
            "context_layer_id": "permanent_water_context_v1_empty_sensitivity",
            "source_roles": "jrc_occurrence+jrc_seasonality",
            "allowed_for_blinded_review_candidate": "false",
            "eligible_for_current_context_layers_csv": "false",
        },
        {
            "context_layer_id": "slope",
            "source_roles": "copernicus_dem",
            "allowed_for_blinded_review_candidate": "true",
            "eligible_for_current_context_layers_csv": "true",
        },
    ]
    for row in context_rows:
        row.update(
            {
                "rights_review_status": "review_pending",
                "processing_allowed": "false",
                "ml_label_derivation_allowed": "false",
                "redistribution_status": "not_assessed_no_redistribution",
                "query_model_only": "true",
                "eligible_for_decision_layer": "false",
                "eligible_for_fpps": "false",
                "eligible_for_warning": "false",
                "assumptions": "Static reviewer context only; not flood truth.",
            }
        )
    _write_csv(root / "aligned_context_inventory.csv", context_fields, context_rows)

    role_fields = [
        "role_id",
        "required_role",
        "assignee_status",
        "assignee",
        "approval_scope",
        "approval_status",
        "approved_at_utc",
        "evidence_reference",
        "blocking_stage",
        "blocker",
        "next_action",
    ]
    role_ids = (
        "RIGHTS-OWNER",
        "REFERENCE-AUTHORITY",
        "REVIEWER-A",
        "REVIEWER-B",
        "ADJUDICATOR-C",
    )
    _write_csv(
        root / "human_role_approval_ledger.csv",
        role_fields,
        [
            {
                "role_id": role_id,
                "required_role": role_id.lower(),
                "assignee_status": "tbd",
                "assignee": "TBD",
                "approval_scope": "pending",
                "approval_status": "not_reviewed",
                "approved_at_utc": "",
                "evidence_reference": "none",
                "blocking_stage": "formal_review",
                "blocker": "Role is unassigned.",
                "next_action": "Assign role.",
            }
            for role_id in role_ids
        ],
    )
    decision_fields = [
        "decision_id",
        "decision",
        "scope_status",
        "authority_type",
        "canonical_rights_effect",
        "recorded_at_utc",
        "notes",
    ]
    _write_csv(
        root / "pilot_scope_decisions.csv",
        decision_fields,
        [
            {
                "decision_id": "PAIR-001",
                "decision": "Use approved Sentinel pair",
                "scope_status": "approved_project_scope",
                "authority_type": "user_instruction",
                "canonical_rights_effect": "none",
                "recorded_at_utc": TECHNICAL_TIME,
                "notes": "Does not substitute for rights review.",
            }
        ],
    )
    (root / "safe_manifest_inventory.csv").write_text(
        "product_id,sha256\nSAFE,abc\n", encoding="utf-8"
    )
    _write_csv(
        root / "processed_sar_inventory.csv",
        [
            "asset_id",
            "sha256",
            "rights_review_status",
            "query_model_only",
            "eligible_for_decision_layer",
            "eligible_for_fpps",
            "eligible_for_warning",
            "assumptions",
        ],
        [
            {
                "asset_id": "RTC",
                "sha256": "def",
                "rights_review_status": "review_pending",
                "query_model_only": "true",
                "eligible_for_decision_layer": "false",
                "eligible_for_fpps": "false",
                "eligible_for_warning": "false",
                "assumptions": "Technical provenance only.",
            }
        ],
    )
    (root / "canonical_gate_check.json").write_text(
        json.dumps({"gate": "blocked_pending_rights"}) + "\n", encoding="utf-8"
    )
    (root / "README.md").write_text("# Pending package\n", encoding="utf-8")

    artifact_roles = {
        "aligned_context_inventory.csv": "context",
        "canonical_gate_check.json": "gate",
        "events.csv": "events",
        "human_role_approval_ledger.csv": "roles",
        "pilot_scope_decisions.csv": "decisions",
        "processed_sar_inventory.csv": "processed",
        "README.md": "readme",
        "safe_manifest_inventory.csv": "safe",
        "source_assets.csv": "sources",
    }
    manifest_rows = []
    for name, role in sorted(artifact_roles.items()):
        artifact = root / name
        manifest_rows.append(
            {
                "file_name": name,
                "file_size_bytes": artifact.stat().st_size,
                "sha256": _sha256(artifact),
                "artifact_role": role,
                "immutable_status": "frozen_pending_v1",
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
        manifest_rows,
    )
    return root


def test_builds_conditioned_clearance_and_preserves_technical_timestamps(
    tmp_path: Path,
) -> None:
    pending = _pending_package(tmp_path / "pending")
    output = build_rights_clearance_package(
        pending, tmp_path / "governance_cleared_v1", _decision()
    )

    seal = validate_rights_clearance_package(output)
    assert seal["decision_timestamp_utc"] == DECLARED_TIME
    assert seal["timestamp_basis"] == TIMESTAMP_BASIS
    assert seal["redistribution_status"] == "YES_WITH_CONDITIONS"
    assert seal["validation_allowed"] is False
    assert seal["eligible_for_fpps"] is False

    event = _read_csv(output / "events.csv")[0]
    assert event["processing_allowed"] == "true"
    assert event["ml_label_derivation_allowed"] == "true"
    assert event["validation_allowed"] == "false"
    assert event["source_timestamp"] == TECHNICAL_TIME
    assert "accountable rights and reference approvals remain unsigned" not in event[
        "assumptions"
    ]
    assert "accountable source-rights approval are recorded" in event["assumptions"]
    source = _read_csv(output / "source_assets.csv")[0]
    assert source["source_timestamp"] == TECHNICAL_TIME
    assert source["redistribution_status"] == "YES_WITH_CONDITIONS"
    assert SENTINEL_MODIFIED_NOTICE in source["assumptions"]

    rights = {
        row["source_id"]: row
        for row in _read_csv(output / "source_rights_decisions_v1.csv")
    }
    assert rights["sentinel1"]["raw_attribution_notice"] == SENTINEL_RAW_NOTICE
    assert rights["sentinel1"]["modified_attribution_notice"] == SENTINEL_MODIFIED_NOTICE
    assert rights["jrc_global_surface_water"]["raw_attribution_notice"] == JRC_ATTRIBUTION
    assert rights["esa_worldcover_2021"]["raw_attribution_notice"] == WORLDCOVER_ATTRIBUTION
    copdem = rights["copernicus_dem_glo30"]
    assert copdem["raw_attribution_notice"] == COPDEM_RAW_NOTICE
    assert copdem["modified_attribution_notice"] == COPDEM_MODIFIED_NOTICE
    assert COPDEM_ARTICLE_6C_NOTICE in copdem["mandatory_conditions"]
    assert rights["mbrsc_sentinel_asia_reference"]["rights_status"] == (
        "excluded_pending_separate_permission"
    )
    assert rights["mbrsc_sentinel_asia_reference"]["local_processing"] == "False"

    context = {
        row["context_layer_id"]: row
        for row in _read_csv(output / "aligned_context_inventory.csv")
    }
    assert context["land_cover"]["processing_allowed"] == "true"
    sensitivity = context["permanent_water_context_v1_empty_sensitivity"]
    assert sensitivity["allowed_for_blinded_review_candidate"] == "false"
    assert sensitivity["eligible_for_current_context_layers_csv"] == "false"
    assert sensitivity["eligible_for_decision_layer"] == "false"

    processed = _read_csv(output / "processed_sar_inventory.csv")
    assert all(
        row["rights_review_status"] == "approved_with_provider_conditions"
        for row in processed
    )

    normalized_decision = json.loads(
        (output / "rights_owner_decision_input_v1.json").read_text(encoding="utf-8")
    )
    assert normalized_decision["decision_timestamp_utc"] == DECLARED_TIME

    roles = {row["role_id"]: row for row in _read_csv(output / "human_role_approval_ledger.csv")}
    assert roles["RIGHTS-OWNER"]["assignee"] == "I Putu Pramana Putra"
    assert roles["RIGHTS-OWNER"]["approved_at_utc"] == DECLARED_TIME
    assert roles["RIGHTS-OWNER"]["evidence_reference"].startswith(
        "rights_owner_declaration_v1.md"
    )
    for role_id in ("REFERENCE-AUTHORITY", "REVIEWER-A", "REVIEWER-B", "ADJUDICATOR-C"):
        assert roles[role_id]["assignee"] == "TBD"
        assert roles[role_id]["assignee_status"] == "tbd"

    decisions = _read_csv(output / "pilot_scope_decisions.csv")
    assert [row["decision_id"] for row in decisions] == ["PAIR-001", "RIGHTS-001"]
    assert decisions[-1]["recorded_at_utc"] == DECLARED_TIME
    assert _sha256(output / "safe_manifest_inventory.csv") == _sha256(
        pending / "safe_manifest_inventory.csv"
    )
    original_processed = _read_csv(pending / "processed_sar_inventory.csv")[0]
    cleared_processed = processed[0]
    for field in (
        "asset_id",
        "sha256",
        "query_model_only",
        "eligible_for_decision_layer",
        "eligible_for_fpps",
        "eligible_for_warning",
    ):
        assert cleared_processed[field] == original_processed[field]


def test_rejects_tampered_pending_package_before_writing(tmp_path: Path) -> None:
    pending = _pending_package(tmp_path / "pending")
    with (pending / "events.csv").open("a", encoding="utf-8") as handle:
        handle.write("tampered\n")
    output = tmp_path / "governance_cleared_v1"

    with pytest.raises(RightsClearanceError, match="size mismatch"):
        build_rights_clearance_package(pending, output, _decision())
    assert not output.exists()


def test_rejects_existing_output_without_modifying_it(tmp_path: Path) -> None:
    pending = _pending_package(tmp_path / "pending")
    output = tmp_path / "cleared"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("user content", encoding="utf-8")

    with pytest.raises(RightsClearanceError, match="already exists"):
        build_rights_clearance_package(pending, output, _decision())
    assert marker.read_text(encoding="utf-8") == "user content"


def test_rejects_unversioned_output_name(tmp_path: Path) -> None:
    pending = _pending_package(tmp_path / "pending")
    with pytest.raises(RightsClearanceError, match="governance_cleared_v"):
        build_rights_clearance_package(pending, tmp_path / "cleared", _decision())


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.update(schema="wrong"), "Decision schema"),
        (
            lambda value: value["sources"]["sentinel1"].update(  # type: ignore[index]
                local_processing="YES"
            ),
            "JSON boolean",
        ),
        (
            lambda value: value["sources"]["sentinel1"].update(  # type: ignore[index]
                redistribution_requested=False
            ),
            "cannot produce a cleared package",
        ),
        (
            lambda value: value.update(decision_timestamp_utc="2026-07-11 03:40 UTC"),
            "exact YYYY-MM-DD",
        ),
    ],
)
def test_decision_contract_is_strict_and_fail_closed(mutation, message: str) -> None:
    value = _decision()
    mutation(value)
    with pytest.raises(RightsClearanceError, match=message):
        RightsOwnerDecision.from_mapping(value)


def test_validator_detects_cleared_artifact_tampering(tmp_path: Path) -> None:
    output = build_rights_clearance_package(
        _pending_package(tmp_path / "pending"),
        tmp_path / "governance_cleared_v1",
        _decision(),
    )
    with (output / "events.csv").open("a", encoding="utf-8") as handle:
        handle.write("tampered\n")
    with pytest.raises(RightsClearanceError, match="size mismatch"):
        validate_rights_clearance_package(output)


def test_registry_binding_requires_exact_governed_csv_bytes(tmp_path: Path) -> None:
    output = build_rights_clearance_package(
        _pending_package(tmp_path / "pending"),
        tmp_path / "governance_cleared_v1",
        _decision(),
    )
    altered_events = tmp_path / "events.csv"
    text = (output / "events.csv").read_text(encoding="utf-8")
    altered_events.write_text(text.replace("\n", "\r\n"), encoding="utf-8")

    with pytest.raises(RightsClearanceError, match="byte-identical"):
        validate_cleared_registry_binding(
            output,
            altered_events,
            output / "source_assets.csv",
        )


@pytest.mark.parametrize(
    ("artifact_name", "mutate", "message"),
    [
        (
            "events.csv",
            lambda rows: rows[0].update(validation_allowed="true"),
            "Unsafe or inconsistent fields for event",
        ),
        (
            "source_rights_decisions_v1.csv",
            lambda rows: rows[0].update(local_processing="False"),
            "Source-rights semantics changed",
        ),
        (
            "human_role_approval_ledger.csv",
            lambda rows: rows[2].update(
                assignee_status="assigned", assignee="Same Solo Operator"
            ),
            "must remain TBD",
        ),
    ],
)
def test_validator_rejects_semantic_tampering_even_after_rehash_and_reseal(
    tmp_path: Path,
    artifact_name: str,
    mutate,
    message: str,
) -> None:
    output = build_rights_clearance_package(
        _pending_package(tmp_path / "pending"),
        tmp_path / "governance_cleared_v1",
        _decision(),
    )
    path = output / artifact_name
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or ())
        rows = list(reader)
    mutate(rows)
    _write_csv(path, fields, rows)
    _resign_after_content_change(output, artifact_name)

    with pytest.raises(RightsClearanceError, match=message):
        validate_rights_clearance_package(output)


def test_cli_builds_package_and_reports_remaining_gates(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    pending = _pending_package(tmp_path / "pending")
    decision_path = tmp_path / "decision.json"
    decision_path.write_text(json.dumps(_decision()), encoding="utf-8")
    output = tmp_path / "governance_cleared_v1"

    result = subprocess.run(
        [
            sys.executable,
            str(repo / "scripts" / "build_label_factory_rights_clearance.py"),
            "--pending-package",
            str(pending),
            "--decision-json",
            str(decision_path),
            "--output",
            str(output),
        ],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "YES_WITH_CONDITIONS" in result.stdout
    assert "reference authority, reviewers, adjudicator, validation" in result.stdout
    validate_rights_clearance_package(output)
