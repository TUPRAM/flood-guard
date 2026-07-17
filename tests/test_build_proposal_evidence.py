from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_proposal_evidence.py"
CHECK_SCRIPT = ROOT / "scripts" / "run_check_with_junit.py"
SCHEMA = ROOT / "packages" / "contracts" / "schemas" / "proposal-evidence.schema.json"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_proposal_evidence", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_check_with_junit", CHECK_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _template(relative_path: str) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "generated_at": "2026-07-01T00:00:00Z",
        "git_commit": "a" * 40,
        "dataset_mode": "fixture_demo",
        "operational_status": "non_operational",
        "artifacts": [
            {
                "kind": "test_fixture",
                "relative_path": relative_path,
                "media_type": "text/plain",
                "sha256": "0" * 64,
            }
        ],
        "test_suites": [
            {
                "name": "root",
                "command": "uv run pytest",
                "result": "not_run",
                "passed": 0,
                "skipped": 0,
            }
        ],
        "geoai_proof": {
            "geoai_version": "0.41.1",
            "feature_stack_id": "synthetic-eight-band-v1",
            "preprocessing_id": "clip_linear_uint8_v1",
            "input_manifest_sha256": None,
            "output_probability_sha256": None,
            "validation_status": "not_run",
            "aggregation_status": "not_run",
            "processing_allowed": False,
            "can_feed_decision_layer": False,
            "reason_blocked": "Synthetic proof has not run.",
        },
    }


def test_parse_junit_receipt_counts_passed_and_skipped(tmp_path: Path) -> None:
    module = _module()
    receipt = tmp_path / "pytest.xml"
    receipt.write_text(
        '<testsuites tests="12" failures="0" errors="0" skipped="2" time="1.2" />',
        encoding="utf-8",
    )
    assert module.parse_junit_receipt(receipt) == {
        "result": "passed",
        "passed": 10,
        "skipped": 2,
    }


def test_build_manifest_rehashes_artifacts_and_merges_receipts(tmp_path: Path) -> None:
    module = _module()
    repository = tmp_path / "repository"
    artifact = repository / "evidence" / "proof.txt"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("reviewable proof\n", encoding="utf-8")
    junit = tmp_path / "junit.xml"
    junit.write_text(
        '<testsuite tests="3" failures="0" errors="0" skipped="1" />',
        encoding="utf-8",
    )

    manifest = module.build_manifest(
        _template("evidence/proof.txt"),
        repository_root=repository,
        junit_by_suite={"root": junit},
        git_commit="A" * 40,
        generated_at="2026-07-17T08:00:00Z",
        require_all_passed=True,
    )
    module.validate_manifest(manifest, SCHEMA)

    assert manifest["git_commit"] == "a" * 40
    assert manifest["artifacts"][0]["sha256"] == module.file_sha256(artifact)
    assert manifest["test_suites"][0] == {
        "name": "root",
        "command": "uv run pytest",
        "result": "passed",
        "passed": 2,
        "skipped": 1,
    }
    assert str(repository.resolve()) not in json.dumps(manifest)


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../secret.txt",
        "nested/../../secret.txt",
        r"C:\\Users\\operator\\secret.txt",
        r"\\\\server\\private\\secret.txt",
        "/home/operator/secret.txt",
    ],
)
def test_build_manifest_rejects_private_or_escaping_artifact_paths(
    tmp_path: Path,
    unsafe_path: str,
) -> None:
    module = _module()
    with pytest.raises(module.EvidenceBuildError):
        module.build_manifest(
            _template(unsafe_path),
            repository_root=tmp_path,
            junit_by_suite={},
            git_commit="a" * 40,
            generated_at="2026-07-17T08:00:00Z",
        )


def test_build_manifest_fails_closed_for_missing_or_failed_suite(tmp_path: Path) -> None:
    module = _module()
    artifact = tmp_path / "proof.txt"
    artifact.write_text("proof\n", encoding="utf-8")
    template = _template("proof.txt")

    with pytest.raises(module.EvidenceBuildError, match="not all passed"):
        module.build_manifest(
            template,
            repository_root=tmp_path,
            junit_by_suite={},
            git_commit="a" * 40,
            generated_at="2026-07-17T08:00:00Z",
            require_all_passed=True,
        )

    failed = tmp_path / "failed.xml"
    failed.write_text(
        '<testsuite tests="2" failures="1" errors="0" skipped="0" />',
        encoding="utf-8",
    )
    with pytest.raises(module.EvidenceBuildError, match="not all passed"):
        module.build_manifest(
            deepcopy(template),
            repository_root=tmp_path,
            junit_by_suite={"root": failed},
            git_commit="a" * 40,
            generated_at="2026-07-17T08:00:00Z",
            require_all_passed=True,
        )


def test_non_test_check_wrapper_writes_machine_readable_status(tmp_path: Path) -> None:
    check = _check_module()
    builder = _module()
    receipt = tmp_path / "check.xml"
    exit_code = check.run_check(
        "frontend",
        receipt,
        [str(Path(__import__("sys").executable)), "-c", "print('verified')"],
    )
    assert exit_code == 0
    assert builder.parse_junit_receipt(receipt) == {
        "result": "passed",
        "passed": 1,
        "skipped": 0,
    }


def test_write_manifest_uses_portable_lf_bytes(tmp_path: Path) -> None:
    module = _module()
    output = tmp_path / "manifest.json"

    module.write_manifest({"schema_version": "1.0", "label": "portable"}, output)

    content = output.read_bytes()
    assert content.endswith(b"\n")
    assert b"\r\n" not in content


def test_builder_derives_geoai_summary_from_checksum_valid_receipt(tmp_path: Path) -> None:
    module = _module()
    thumbnail = tmp_path / "evidence" / "proof.png"
    thumbnail.parent.mkdir()
    thumbnail.write_bytes(b"small png fixture")
    thumbnail_sha = module.file_sha256(thumbnail)
    proof = {
        "floodguard_commit": "a" * 40,
        "proof_scope": "synthetic_integration_only",
        "dataset_mode": "candidate",
        "operational_status": "non_operational",
        "official_warning": False,
        "execution_mode": "real_geoai_smoke",
        "training_execution": "model_construction_only",
        "actual_geoai_calls": [
            "geoai.utils.training.export_geotiff_tiles",
            "geoai.inference.predict_geotiff",
        ],
        "claim_boundary": (
            "Synthetic integration proof; not evidence of real flood-detection accuracy."
        ),
        "geoai_version": "0.41.1",
        "feature_stack": {
            "feature_stack_id": "bound-eight-band",
            "preprocessing_id": "clip_linear_uint8_v1",
            "input_manifest_sha256": "1" * 64,
        },
        "probability": {
            "sha256": "2" * 64,
            "class_index": 1,
            "band_name": "flood_probability_0_1",
            "dtype": "float32",
            "valid_pixel_count": 64,
        },
        "validation_checks": {"crs": True, "range": True},
        "aggregation": {
            "status": "report_only",
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "sample_pixel_count": 64,
        },
        "thumbnail": {"sha256": thumbnail_sha},
        "processing_allowed": True,
        "can_feed_decision_layer": False,
        "reason_blocked": "Synthetic proof is report-only.",
    }
    proof["receipt_payload_sha256"] = module._canonical_sha256(proof)
    receipt = tmp_path / "evidence" / "proof.json"
    receipt.write_text(json.dumps(proof), encoding="utf-8")
    template = _template("evidence/proof.json")
    template["artifacts"] = [
        {
            "kind": "geoai_proof_receipt",
            "relative_path": "evidence/proof.json",
            "media_type": "application/json",
            "sha256": "0" * 64,
        },
        {
            "kind": "geoai_probability_thumbnail",
            "relative_path": "evidence/proof.png",
            "media_type": "image/png",
            "sha256": "0" * 64,
        },
    ]
    template["geoai_proof"]["output_probability_sha256"] = "9" * 64

    manifest = module.build_manifest(
        template,
        repository_root=tmp_path,
        junit_by_suite={},
        git_commit="a" * 40,
        generated_at="2026-07-17T08:00:00Z",
    )
    module.validate_manifest(manifest, SCHEMA)
    assert manifest["geoai_proof"] == {
        "geoai_version": "0.41.1",
        "feature_stack_id": "bound-eight-band",
        "preprocessing_id": "clip_linear_uint8_v1",
        "input_manifest_sha256": "1" * 64,
        "output_probability_sha256": "2" * 64,
        "validation_status": "passed",
        "aggregation_status": "report_only",
        "processing_allowed": True,
        "can_feed_decision_layer": False,
        "reason_blocked": "Synthetic proof is report-only.",
    }


@pytest.mark.parametrize(
    ("field_path", "replacement"),
    [
        (("floodguard_commit",), "b" * 40),
        (("proof_scope",), "decision_ready"),
        (("aggregation", "eligible_for_fpps"), True),
        (("validation_checks", "crs"), False),
    ],
)
def test_builder_rejects_rehashed_geoai_safety_substitution(
    tmp_path: Path,
    field_path: tuple[str, ...],
    replacement: object,
) -> None:
    module = _module()
    thumbnail = tmp_path / "evidence" / "proof.png"
    thumbnail.parent.mkdir()
    thumbnail.write_bytes(b"small png fixture")
    proof = {
        "floodguard_commit": "a" * 40,
        "proof_scope": "synthetic_integration_only",
        "dataset_mode": "candidate",
        "operational_status": "non_operational",
        "official_warning": False,
        "execution_mode": "real_geoai_smoke",
        "training_execution": "model_construction_only",
        "actual_geoai_calls": [
            "geoai.utils.training.export_geotiff_tiles",
            "geoai.inference.predict_geotiff",
        ],
        "claim_boundary": (
            "Synthetic integration proof; not evidence of real flood-detection accuracy."
        ),
        "geoai_version": "0.41.1",
        "feature_stack": {
            "feature_stack_id": "bound-eight-band",
            "preprocessing_id": "clip_linear_uint8_v1",
            "input_manifest_sha256": "1" * 64,
        },
        "probability": {
            "sha256": "2" * 64,
            "class_index": 1,
            "band_name": "flood_probability_0_1",
            "dtype": "float32",
            "valid_pixel_count": 64,
        },
        "validation_checks": {"crs": True, "range": True},
        "aggregation": {
            "status": "report_only",
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "sample_pixel_count": 64,
        },
        "thumbnail": {"sha256": module.file_sha256(thumbnail)},
        "processing_allowed": True,
        "can_feed_decision_layer": False,
        "reason_blocked": "Synthetic proof is report-only.",
    }
    target = proof
    for key in field_path[:-1]:
        target = target[key]
    target[field_path[-1]] = replacement
    proof["receipt_payload_sha256"] = module._canonical_sha256(proof)
    receipt = tmp_path / "evidence" / "proof.json"
    receipt.write_text(json.dumps(proof), encoding="utf-8")
    template = _template("evidence/proof.json")
    template["artifacts"] = [
        {
            "kind": "geoai_proof_receipt",
            "relative_path": "evidence/proof.json",
            "media_type": "application/json",
            "sha256": "0" * 64,
        },
        {
            "kind": "geoai_probability_thumbnail",
            "relative_path": "evidence/proof.png",
            "media_type": "image/png",
            "sha256": "0" * 64,
        },
    ]

    with pytest.raises(module.EvidenceBuildError, match="fail-closed"):
        module.build_manifest(
            template,
            repository_root=tmp_path,
            junit_by_suite={},
            git_commit="a" * 40,
            generated_at="2026-07-17T08:00:00Z",
        )
