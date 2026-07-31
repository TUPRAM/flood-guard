from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "sign_controlled_model_run.py"
RUNTIME_PROFILE = {
    "training_seconds": 12.5,
    "calibration_seconds": 1.0,
    "inference_seconds": 2.0,
    "total_seconds": 15.5,
    "peak_memory_mb": 384.0,
    "device": "cpu",
    "hardware_class": "test-workstation",
}


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "sign_controlled_model_run_cli_under_test",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _arguments(tmp_path: Path) -> list[str]:
    runtime = tmp_path / "runtime.json"
    runtime.write_text(json.dumps(RUNTIME_PROFILE), encoding="utf-8")
    public_key = tmp_path / "external-authority-public-key.hex"
    public_key.write_text(
        "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
        encoding="ascii",
    )
    return [
        str(SCRIPT_PATH),
        "--acquisition-manifest",
        str(tmp_path / "acquisition.csv"),
        "--acquisition-authority-receipt",
        str(tmp_path / "authority.json"),
        "--artifact",
        f"pre_event_sar={tmp_path / 'pre.safe'}",
        "--artifact",
        f"post_event_sar={tmp_path / 'post.safe'}",
        "--artifact",
        f"reference_mask={tmp_path / 'reference.tif'}",
        "--reviewer-qualification-receipt",
        str(tmp_path / "reviewer-qualification.json"),
        "--holdout-receipt",
        str(tmp_path / "holdout.json"),
        "--holdout-geometry",
        str(tmp_path / "holdout.geojson"),
        "--holdout-grid-contract",
        str(tmp_path / "grid.json"),
        "--holdout-membership",
        str(tmp_path / "membership.csv"),
        "--reference-cell-receipt",
        str(tmp_path / "reference-receipt.json"),
        "--reference-cell-evidence",
        str(tmp_path / "reference-cells.csv"),
        "--calibration-reference",
        str(tmp_path / "calibration-reference.csv"),
        "--error-strata",
        str(tmp_path / "error-strata.csv"),
        "--promotion-policy",
        str(tmp_path / "promotion-policy.json"),
        "--execution-authorization-receipt",
        str(tmp_path / "execution-authorization.json"),
        "--model-id",
        "SAR-BASELINE-V1",
        "--model-family",
        "deterministic_sar_baseline",
        "--model-artifact",
        str(tmp_path / "model.bin"),
        "--model-contract",
        str(tmp_path / "model-contract.json"),
        "--calibration-prediction",
        str(tmp_path / "calibration-prediction.csv"),
        "--threshold-selection-receipt",
        str(tmp_path / "threshold-receipt.json"),
        "--prediction",
        str(tmp_path / "prediction.csv"),
        "--runtime-profile",
        str(runtime),
        "--inference-started-at-utc",
        "2024-01-03T00:00:00Z",
        "--completed-at-utc",
        "2024-01-04T00:00:00Z",
        "--assumptions",
        "Qualified evidence test.",
        "--trusted-key",
        "acquisition-authority-v1=FG_ACQUISITION_KEY",
        "--trusted-external-authority-key",
        f"external-authority-v1={public_key}",
        "--signing-key-id",
        "model-executor-v1",
        "--signing-key-env",
        "FG_MODEL_KEY",
        "--output",
        str(tmp_path / "model-run.json"),
    ]


def test_cli_exposes_calibration_only_authorized_interface() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--runtime-profile" in completed.stdout
    assert "--reviewer-qualification-receipt" in completed.stdout
    assert "--execution-authorization-receipt" in completed.stdout
    assert "--calibration-prediction" in completed.stdout
    assert "--threshold-selection-receipt" in completed.stdout
    assert "--decision-threshold" not in completed.stdout
    assert "--threshold-selected-at-utc" not in completed.stdout
    assert "--signing-key " not in completed.stdout
    assert "never imports GeoAI or" in completed.stdout
    assert "PyTorch" in completed.stdout


@pytest.mark.parametrize(
    "payload, message",
    [
        (
            {key: value for key, value in RUNTIME_PROFILE.items() if key != "device"},
            "missing=device",
        ),
        ({**RUNTIME_PROFILE, "gpu_name": "none"}, "unexpected=gpu_name"),
        ([RUNTIME_PROFILE], "must be a JSON object"),
    ],
)
def test_runtime_profile_requires_exact_object_keys(
    tmp_path: Path,
    payload: object,
    message: str,
) -> None:
    module = _load_script()
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        module._load_runtime_profile(path)


def test_runtime_profile_rejects_duplicate_keys(tmp_path: Path) -> None:
    module = _load_script()
    path = tmp_path / "runtime.json"
    path.write_text(
        '{"training_seconds":1,"training_seconds":2}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate key: training_seconds"):
        module._load_runtime_profile(path)


def test_cli_fails_closed_without_external_signing_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script()
    monkeypatch.setattr(sys, "argv", _arguments(tmp_path))
    monkeypatch.delenv("FG_ACQUISITION_KEY", raising=False)
    monkeypatch.delenv("FG_MODEL_KEY", raising=False)

    assert module.main() == 2

    output = capsys.readouterr().out
    assert "BLOCKED:" in output
    assert "environment variable is missing" in output
    assert "operational_status=non_operational" in output
    assert "can_feed_decision_layer=false" in output
    assert not (tmp_path / "model-run.json").exists()


def test_cli_verifies_full_lineage_and_issues_report_only_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script()
    monkeypatch.setattr(sys, "argv", _arguments(tmp_path))
    monkeypatch.setenv("FG_ACQUISITION_KEY", "acquisition-test-key")
    monkeypatch.setenv("FG_MODEL_KEY", "model-test-key")

    acquisition = SimpleNamespace(ready=True, blockers=())
    reviewer = object()
    holdout = object()
    reference = object()
    calibration = object()
    execution = object()
    calls: list[str] = []

    def assess(*_args: object, **kwargs: object) -> object:
        calls.append("acquisition")
        assert kwargs["signing_keys"] == {
            "acquisition-authority-v1": b"acquisition-test-key",
            "model-executor-v1": b"model-test-key",
        }
        assert set(kwargs["external_authority_public_keys"]) == {
            "external-authority-v1"
        }
        return acquisition

    def load_reviewer(*_args: object, **kwargs: object) -> object:
        calls.append("reviewer")
        assert kwargs["acquisition"] is acquisition
        return reviewer

    def load_holdout(*_args: object, **_kwargs: object) -> object:
        calls.append("holdout")
        return holdout

    def load_reference(*_args: object, **kwargs: object) -> object:
        calls.append("reference")
        assert kwargs["reviewer_qualification"] is reviewer
        assert kwargs["holdout"] is holdout
        return reference

    def load_calibration(*_args: object, **kwargs: object) -> object:
        calls.append("calibration")
        assert kwargs["reviewer_qualification"] is reviewer
        return calibration

    def load_execution(*_args: object, **kwargs: object) -> object:
        calls.append("execution")
        assert kwargs["reference_cells"] is reference
        return execution

    def write_manifest(**kwargs: object) -> dict[str, object]:
        calls.append("model_run")
        assert kwargs["acquisition"] is acquisition
        assert kwargs["reviewer_qualification"] is reviewer
        assert kwargs["holdout"] is holdout
        assert kwargs["reference_cells"] is reference
        assert kwargs["calibration_reference"] is calibration
        assert kwargs["execution_authorization"] is execution
        assert kwargs["runtime_profile"] == RUNTIME_PROFILE
        assert kwargs["signing_key"] == b"model-test-key"
        assert kwargs["signing_key_id"] == "model-executor-v1"
        return {"manifest_sha256": "b" * 64}

    monkeypatch.setattr(module, "assess_acquisition_manifest", assess)
    monkeypatch.setattr(
        module, "load_signed_reviewer_qualification_receipt", load_reviewer
    )
    monkeypatch.setattr(module, "load_spatial_holdout", load_holdout)
    monkeypatch.setattr(module, "load_signed_reference_cell_evidence", load_reference)
    monkeypatch.setattr(
        module, "load_signed_calibration_reference_evidence", load_calibration
    )
    monkeypatch.setattr(
        module, "load_signed_execution_authorization_receipt", load_execution
    )
    monkeypatch.setattr(module, "write_signed_model_run_manifest", write_manifest)

    assert module.main() == 0

    assert calls == [
        "acquisition",
        "reviewer",
        "holdout",
        "reference",
        "calibration",
        "execution",
        "model_run",
    ]
    output = capsys.readouterr().out
    assert "manifest_sha256=" + "b" * 64 in output
    assert "delivery_scope=report_only" in output
    assert "operational_status=non_operational" in output
    assert "can_feed_decision_layer=false" in output
    assert "official_warning=false" in output


def test_cli_rejects_conflicting_output_signing_key_declaration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script()
    arguments = _arguments(tmp_path)
    trusted_index = arguments.index("acquisition-authority-v1=FG_ACQUISITION_KEY")
    arguments[trusted_index] = "model-executor-v1=FG_CONFLICTING_MODEL_KEY"
    monkeypatch.setattr(sys, "argv", arguments)
    monkeypatch.setenv("FG_CONFLICTING_MODEL_KEY", "wrong-model-key")
    monkeypatch.setenv("FG_MODEL_KEY", "model-test-key")

    assert module.main() == 2
    assert "conflicts with the trusted key declaration" in capsys.readouterr().out
