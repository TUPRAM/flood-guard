from __future__ import annotations

import base64
import gzip
import json
from pathlib import Path
import re
import subprocess
import sys

import pandas as pd
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "script_name",
    [
        "issue_controlled_acquisition_authority_receipt.py",
        "sign_controlled_reviewer_qualification.py",
        "freeze_controlled_spatial_partitions.py",
        "sign_controlled_reference_cells.py",
        "audit_controlled_three_model_experiment.py",
        "issue_controlled_execution_authorization_receipt.py",
        "select_controlled_model_threshold.py",
        "sign_controlled_model_run.py",
        "run_controlled_three_model_experiment.py",
    ],
)
def test_controlled_experiment_operator_scripts_expose_help(
    script_name: str,
) -> None:
    completed = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / script_name), "--help"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "usage:" in completed.stdout


@pytest.mark.parametrize(
    ("script_name", "basename_expression"),
    [
        ("build_reference_authority_approval.py", "package.name"),
        ("build_reference_authority_approval.py", "args.package.name"),
        ("build_reviewer_calibration_receipt.py", "args.output.name"),
        (
            "build_reviewer_calibration_failure_diagnostic.py",
            "args.output.name",
        ),
        ("freeze_label_factory_calibration_reference.py", "outputs.cells.name"),
        (
            "freeze_label_factory_calibration_reference.py",
            "outputs.manifest.name",
        ),
        ("rasterize_calibration_reference.py", "outputs.cells.name"),
        ("rasterize_calibration_reference.py", "outputs.manifest.name"),
        ("plan_label_factory_calibration_reserve.py", "path.name"),
    ],
)
def test_task_relevant_cli_success_messages_use_basenames(
    script_name: str,
    basename_expression: str,
) -> None:
    source = (REPO_ROOT / "scripts" / script_name).read_text(encoding="utf-8")

    assert basename_expression in source


def test_threshold_cli_cannot_request_full_final_holdout_truth() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "select_controlled_model_threshold.py"),
            "--help",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--calibration-reference" in completed.stdout
    assert "--execution-authorization-receipt" in completed.stdout
    assert "--calibration-prediction" in completed.stdout
    assert "--reference-cell-evidence" not in completed.stdout
    assert "--error-strata" not in completed.stdout


def test_holdout_cli_requires_signed_acquisition_lineage() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "freeze_controlled_spatial_partitions.py"),
            "--help",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--acquisition-manifest" in completed.stdout
    assert "--acquisition-authority-receipt" in completed.stdout
    assert "--artifact" in completed.stdout
    assert "--trusted-key" in completed.stdout
    assert "--trusted-external-authority-key" in completed.stdout
    assert "--signing-key-env" in completed.stdout
    assert "--source-registry" not in completed.stdout
    assert "--experiment-id" not in completed.stdout
    assert "--study-area" not in completed.stdout


def test_reviewer_qualification_cli_requires_exact_reviewer_cells() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "sign_controlled_reviewer_qualification.py"),
            "--help",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--reviewer-cell REVIEWER_ID=PATH" in completed.stdout
    assert "--trusted-external-authority-key" in completed.stdout


def test_controlled_acquisition_manifest_binds_exact_safe_stop_times() -> None:
    manifest = pd.read_csv(
        REPO_ROOT
        / "docs"
        / "validation"
        / "controlled_three_model_acquisition_manifest.csv"
    ).set_index("role")

    assert (
        manifest.loc["pre_event_sar", "acquisition_end_utc"]
        == "2024-09-03T23:16:25.773465Z"
    )
    assert (
        manifest.loc["post_event_sar", "acquisition_end_utc"]
        == "2024-09-15T23:16:26.674888Z"
    )


def test_external_authority_template_cannot_imply_approval() -> None:
    request = json.loads(
        (
            REPO_ROOT
            / "docs"
            / "controlled-experiment"
            / "external_authority_decision_request.template.json"
        ).read_text(encoding="utf-8")
    )

    assert request["decision_status"] == "not_returned_no_approval"
    assert request["no_implied_approval"] is True
    assert {product["role"] for product in request["products"]} == {
        "pre_event_sar",
        "post_event_sar",
        "provider_source_candidate",
        "reference_mask",
    }
    assert all(
        product["authority_decision"] == "unanswered" for product in request["products"]
    )
    assert all(
        set(product["permissions"].values()) == {"unanswered"}
        for product in request["products"]
    )


def test_completed_external_authority_template_matches_executable_shape() -> None:
    template = json.loads(
        (
            REPO_ROOT
            / "docs"
            / "controlled-experiment"
            / "external_authority_completed_decision.template.json"
        ).read_text(encoding="utf-8")
    )

    assert set(template) == {
        "schema_version",
        "decision_id",
        "request_id",
        "experiment_id",
        "study_area",
        "acquisition_manifest_sha256",
        "decision_status",
        "products",
        "required_attribution_and_conditions",
        "authorized_signer",
        "signer_attestations",
        "official_warning",
    }
    assert template["schema_version"] == "floodguard.external_authority_decision.v1"
    assert template["official_warning"] is False
    assert [product["role"] for product in template["products"]] == [
        "pre_event_sar",
        "post_event_sar",
        "reference_mask",
    ]
    product_keys = {
        "role",
        "source_name",
        "source_url",
        "product_id",
        "acquisition_start_utc",
        "acquisition_end_utc",
        "source_timestamp",
        "artifact_sha256",
        "catalog_evidence_sha256",
        "license_evidence_sha256",
        "terms_url",
        "license_status",
        "redistribution_status",
        "reference_mask_status",
        "temporal_alignment_status",
        "assumptions",
        "authority_decision",
        "permissions",
        "reference_qualification",
    }
    permission_keys = {
        "local_analysis",
        "model_input_or_feature_use",
        "ml_label_use",
        "validation_metrics",
        "derived_reporting",
        "screenshots_and_demo_display",
        "source_redistribution",
        "derived_geometry_redistribution",
        "reference_only_storage_if_not_redistributable",
    }
    for product in template["products"]:
        assert set(product) == product_keys
        assert set(product["permissions"]) == permission_keys
        assert all(isinstance(value, bool) for value in product["permissions"].values())
    assert template["products"][0]["reference_qualification"] is None
    assert template["products"][1]["reference_qualification"] is None
    assert set(template["products"][2]["reference_qualification"]) == {
        "status",
        "qualification_method",
        "known_uncertainty_and_error_categories",
        "independent_of_model_inputs",
    }
    assert template["authorized_signer"]["signature_algorithm"] == "Ed25519"
    assert set(template["signer_attestations"].values()) == {True}


def test_acquisition_runbook_uses_external_signature_and_internal_integrity_key() -> (
    None
):
    runbook = (
        REPO_ROOT / "docs" / "controlled-experiment" / "operator-runbook.md"
    ).read_text(encoding="utf-8")
    acquisition_section = runbook.split("## 2. Issue acquisition authority", 1)[
        1
    ].split("## 3. Freeze the blind calibration release", 1)[0]

    assert "--external-authority-decision" in acquisition_section
    assert "--external-authority-signature" in acquisition_section
    assert "--trusted-external-authority-key" in acquisition_section
    assert "--receipt-signing-key-env" in acquisition_section
    assert "--allowlist-id" not in acquisition_section
    assert "--issued-at-utc" not in acquisition_section
    assert "--expires-at-utc" not in acquisition_section


def test_committed_portable_gate_report_matches_blocked_receipt() -> None:
    validation = REPO_ROOT / "docs" / "validation"
    receipt = json.loads(
        (validation / "controlled_three_model_gate_receipt.json").read_text(
            encoding="utf-8"
        )
    )
    artifact = json.loads(
        (
            validation / "controlled_three_model_data_quality_report.artifact.json"
        ).read_text(encoding="utf-8")
    )
    html = (validation / "controlled_three_model_data_quality_report.html").read_text(
        encoding="utf-8"
    )

    assert receipt["artifact_schema"].endswith(".v4")
    assert receipt["gate_kind"] == "pre_execution_readiness"
    assert receipt["gate_status"] == "blocked"
    assert receipt["processing_allowed"] is False
    assert receipt["experiment_executed"] is False
    assert receipt["can_feed_decision_layer"] is False
    assert receipt["official_warning"] is False
    assert len(receipt["blockers"]) == 15
    assert receipt["model_evidence"] == {"status": "not_expected_before_execution"}
    assert artifact["manifest"]["generatedAt"] == receipt["generated_at"]
    assert artifact["snapshot"]["generatedAt"] == receipt["generated_at"]
    assert artifact["snapshot"]["status"] == "blocked"
    assert artifact["snapshot"]["datasets"]["gate_summary"] == [
        {"status": "Verified", "control_count": 3},
        {"status": "Blocked", "control_count": 6},
        {"status": "Deferred", "control_count": 1},
    ]
    gate_status = {
        row["gate"]: row["status"]
        for row in artifact["snapshot"]["datasets"]["gate_status"]
    }
    assert gate_status["Predeclared promotion policy"] == "Blocked"
    assert gate_status["Completed three-model evidence"] == "Deferred"
    assert 'id="floodguard-portable-report-layout-fix"' in html
    assert "FloodGuard Controlled Three-Model Experiment" in html
    assert "C:\\Users\\" not in html
    assert "C:/Users/" not in html
    payload_match = re.search(
        r'<template id="data-analytics-portable-artifact-payload-source" '
        r'data-compression="gzip-base64">\s*([A-Za-z0-9+/=\r\n]+)\s*'
        r"</template>",
        html,
    )
    assert payload_match is not None
    embedded = json.loads(
        gzip.decompress(
            base64.b64decode(re.sub(r"\s+", "", payload_match.group(1)))
        ).decode("utf-8")
    )
    assert embedded["surface"] == artifact["surface"]
    assert embedded["manifest"] == artifact["manifest"]
    assert embedded["snapshot"] == artifact["snapshot"]
    assert embedded["sources"] == artifact["sources"]
