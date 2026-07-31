from __future__ import annotations

import json
import sys
import tomllib
from dataclasses import replace
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

import jsonschema
import pytest
from jsonschema import FormatChecker

from geoai_runner.cli import build_parser, main
from geoai_runner.contract import (
    ContractError,
    GeoAIRunContract,
    ValidationMetricsContract,
)
from geoai_runner.manifest import (
    ManifestError,
    build_public_model_run,
    write_public_model_run,
)

from .helpers import build_synthetic_workspace, write_contract_json


def test_run_contract_round_trip_and_redacted_public_path(tmp_path: Path) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    path = evidence["workspace"] / "contract.json"
    write_contract_json(evidence["contract"], path)
    restored = GeoAIRunContract.from_json(path)
    assert restored == evidence["contract"]
    public = restored.public_dict()
    assert public["external_output_workspace"] == ("external-workspace/geoai-synthetic-proof-001")
    assert str(evidence["workspace"]) not in repr(public)


def test_contract_rejects_gate_overrides_and_unzoned_timestamps(tmp_path: Path) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    contract = evidence["inference_contract"]
    with pytest.raises(ContractError, match="Candidate GeoAI runs"):
        replace(contract, can_feed_decision_layer=True, confidence_class="medium").validate()
    with pytest.raises(ContractError, match="cannot override"):
        replace(
            contract,
            input_manifest_rows=(
                replace(contract.input_manifest_rows[0], processing_allowed=False),
                *contract.input_manifest_rows[1:],
            ),
        ).validate()

    reordered = replace(
        contract,
        input_manifest_rows=tuple(reversed(contract.input_manifest_rows)),
    )
    substituted_rows = (
        replace(contract.input_manifest_rows[0], sha256="0" * 64),
        *contract.input_manifest_rows[1:],
    )
    assert reordered.input_manifest_sha256 == contract.input_manifest_sha256
    assert (
        replace(contract, input_manifest_rows=substituted_rows).input_manifest_sha256
        != contract.input_manifest_sha256
    )
    with pytest.raises(ContractError, match="time and timezone"):
        replace(contract, source_timestamp="2024-09-15T23:16:01").validate()
    with pytest.raises(ContractError, match="spatial holdout"):
        replace(contract, spatial_holdout_ids=()).validate()


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"flood_class_index": True}, "integer class 1"),
        ({"tile_size": True}, "Tile size and overlap"),
        ({"channel_count": 7}, "channel_count must match"),
        ({"official_warning": 0}, "not an official warning"),
        ({"resolution": "10,10"}, "Resolution values"),
        ({"bounds": (0.0, 0.0, 1.0)}, "Bounds must be ordered"),
        ({"reason_blocked": None}, "reason_blocked must be a string"),
    ],
)
def test_contract_rejects_runtime_type_spoofing(
    tmp_path: Path,
    changes: dict[str, object],
    message: str,
) -> None:
    contract = build_synthetic_workspace(tmp_path)["contract"]
    with pytest.raises(ContractError, match=message):
        replace(contract, **changes).validate()


def test_contract_json_rejects_unknown_fields(tmp_path: Path) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    path = evidence["workspace"] / "contract.json"
    write_contract_json(evidence["contract"], path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["bypass_gates"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ContractError, match="bypass_gates"):
        GeoAIRunContract.from_json(path)


@pytest.mark.parametrize(
    "missing_role",
    ["pre_event_sar", "post_event_sar", "terrain_slope", "permanent_water"],
)
def test_processing_contract_requires_channel_provenance_roles(
    tmp_path: Path,
    missing_role: str,
) -> None:
    contract = build_synthetic_workspace(tmp_path)["contract"]
    rows = tuple(row for row in contract.input_manifest_rows if row.role != missing_role)
    with pytest.raises(ContractError, match="provenance role"):
        replace(contract, input_manifest_rows=rows).validate()


def test_processing_contract_rejects_bad_source_receipt_and_event_timing(
    tmp_path: Path,
) -> None:
    contract = build_synthetic_workspace(tmp_path)["contract"]
    bad_checksum_rows = tuple(
        replace(row, sha256="not-a-checksum") if row.role == "terrain_slope" else row
        for row in contract.input_manifest_rows
    )
    with pytest.raises(ContractError, match="lowercase SHA-256"):
        replace(contract, input_manifest_rows=bad_checksum_rows).validate()

    bad_timing_rows = tuple(
        replace(row, source_timestamp="2024-09-09T00:00:00Z")
        if row.role == "post_event_sar"
        else row
        for row in contract.input_manifest_rows
    )
    with pytest.raises(ContractError, match="pre_event_sar < post_event_sar"):
        replace(contract, input_manifest_rows=bad_timing_rows).validate()


def test_spatial_partitions_reject_overlap_and_holdout_receipt_drift(
    tmp_path: Path,
) -> None:
    contract = build_synthetic_workspace(tmp_path)["contract"]
    train, holdout = contract.spatial_partitions
    with pytest.raises(ContractError, match="must not overlap"):
        replace(
            contract,
            spatial_partitions=(
                train,
                replace(
                    holdout,
                    bounds=(600030.0, 2200000.0, 600080.0, 2200080.0),
                ),
            ),
        ).validate()
    with pytest.raises(ContractError, match="exactly match"):
        replace(contract, spatial_holdout_ids=("different-holdout",)).validate()

    with pytest.raises(ContractError, match="tile manifest receipt"):
        replace(
            contract,
            run_status="prepared",
        ).validate()


def test_feedable_contract_requires_complete_bound_validation_metrics(
    tmp_path: Path,
) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    contract = evidence["inference_contract"]
    incomplete = replace(
        contract,
        dataset_mode="official_input",
        operational_status="planning_only",
        confidence_class="medium",
        can_feed_decision_layer=True,
        reason_blocked="",
    )
    with pytest.raises(ContractError, match="complete validation metrics"):
        incomplete.validate()

    metrics = ValidationMetricsContract(
        iou=0.4,
        f1_dice=0.57,
        precision=0.5,
        recall=0.67,
        area_error_ratio=0.2,
        brier_score=0.18,
        expected_calibration_error=0.08,
    )
    feedable = replace(incomplete, validation_metrics=metrics)
    feedable.validate()
    payload = build_public_model_run(feedable)
    assert all(value is not None for value in payload["validation_metrics"].values())
    rejected_output = evidence["workspace"] / "rejected-feedable-manifest.json"
    with pytest.raises(ManifestError, match="complete metrics bound"):
        write_public_model_run(
            rejected_output,
            feedable,
            validation_metrics={"iou": 0.4},
        )
    assert not rejected_output.exists()


def test_public_manifest_matches_shared_schema_and_preserves_candidate_gate(
    tmp_path: Path,
) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    metrics = {
        "iou": 0.4,
        "f1_dice": 0.57,
        "precision": 0.5,
        "recall": 0.67,
        "area_error_ratio": 0.2,
        "brier_score": 0.18,
        "expected_calibration_error": 0.08,
    }
    payload = build_public_model_run(
        evidence["contract"],
        validation_metrics=metrics,
        error_categories=["permanent_water_false_positive", "steep_terrain_review"],
        generated_at=datetime(2026, 7, 16, tzinfo=UTC),
    )
    schema = _shared_model_schema()
    jsonschema.Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    ).validate(payload)
    assert payload["model_family"] == "geoai"
    assert payload["can_feed_decision_layer"] is False
    assert payload["official_warning"] is False
    assert payload["preprocessing"]["value_domain"] == "uint8_0_255"
    assert len(payload["preprocessing"]["transforms"]) == 8
    assert payload["input_manifest_rows"][0]["role"] == "pre_event_sar"
    assert payload["encoded_feature_sha256"] == evidence["contract"].encoded_feature_sha256
    assert payload["reference_mask_sha256"] == evidence["contract"].reference_mask_sha256
    assert payload["prepared_tile_manifest_sha256"] is None
    assert payload["spatial_holdout_ids"] == ["holdout-zone-01"]
    assert [item["split"] for item in payload["spatial_partitions"]] == [
        "train",
        "holdout",
    ]
    assert payload["validation_metrics"]["expected_calibration_error"] == 0.08
    assert not _contains_private_path(payload)


def test_manifest_write_is_canonical_external_and_rejects_bad_metrics(
    tmp_path: Path,
) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    output = evidence["workspace"] / "manifests" / "run.json"
    receipt = write_public_model_run(
        output,
        evidence["contract"],
        generated_at=datetime(2026, 7, 16, tzinfo=UTC),
    )
    assert len(receipt) == 64
    assert output.read_bytes().endswith(b"\n")
    with pytest.raises(ValueError, match="escapes"):
        write_public_model_run(
            tmp_path / "outside.json",
            evidence["contract"],
        )
    with pytest.raises(ManifestError, match="area_error_ratio"):
        build_public_model_run(
            evidence["contract"],
            validation_metrics={"area_error_ratio": -0.1},
        )
    with pytest.raises(ManifestError, match="must be an object"):
        build_public_model_run(
            evidence["contract"],
            validation_metrics=[0.5],
        )
    with pytest.raises(ManifestError, match="array of strings"):
        build_public_model_run(
            evidence["contract"],
            error_categories="steep_terrain_review",
        )


def test_cli_validates_contract_and_encodes_without_importing_geoai(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    contract_path = evidence["workspace"] / "contract.json"
    write_contract_json(evidence["contract"], contract_path)
    assert main(["validate-contract", "--contract", str(contract_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run_id"] == evidence["contract"].run_id

    encoded = evidence["workspace"] / "cli-encoded.tif"
    sidecar = evidence["workspace"] / "cli-sidecar.json"
    assert (
        main(
            [
                "encode",
                "--workspace",
                str(evidence["workspace"]),
                "--input",
                str(evidence["physical"]),
                "--output",
                str(encoded),
                "--sidecar",
                str(sidecar),
            ]
        )
        == 0
    )
    receipt = json.loads(capsys.readouterr().out)
    assert len(receipt["feature_sha256"]) == 64
    assert encoded.is_file() and sidecar.is_file()
    assert "geoai" not in sys.modules


def test_cli_rejects_output_outside_workspace(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    result = main(
        [
            "encode",
            "--workspace",
            str(evidence["workspace"]),
            "--input",
            str(evidence["physical"]),
            "--output",
            str(tmp_path / "outside.tif"),
            "--sidecar",
            str(evidence["workspace"] / "sidecar-2.json"),
        ]
    )
    assert result == 2
    assert "escapes" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["validate-grid", "export-tiles"])
def test_grid_cli_commands_require_explicit_sidecar(command: str) -> None:
    parser = build_parser()
    arguments = [
        command,
        "--contract",
        "run.json",
        "--features",
        "features.tif",
        "--mask",
        "mask.tif",
        "--sidecar",
        "transform.json",
    ]
    if command == "export-tiles":
        arguments.extend(("--output-dir", "tiles"))
    parsed = parser.parse_args(arguments)
    assert parsed.sidecar == Path("transform.json")


def test_root_dependencies_and_normal_import_remain_geoai_free() -> None:
    root = Path(__file__).resolve().parents[3]
    root_project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    root_dependencies = root_project["project"]["dependencies"]
    assert not any("geoai" in dependency.lower() for dependency in root_dependencies)
    assert not any("torch" in dependency.lower() for dependency in root_dependencies)
    assert "geoai" not in sys.modules

    runner_project = tomllib.loads(
        (root / "services" / "geoai-runner" / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert "geoai-py==0.41.1" in runner_project["project"]["optional-dependencies"]["geoai"]


def test_lock_pins_python_and_geoai_only_inside_runner() -> None:
    root = Path(__file__).resolve().parents[3]
    lock_path = root / "services" / "geoai-runner" / "uv.lock"
    assert lock_path.is_file()
    lock = lock_path.read_text(encoding="utf-8")
    assert 'requires-python = "==3.12.*"' in lock
    assert 'name = "geoai-py"' in lock
    assert 'version = "0.41.1"' in lock
    assert 'name = "segmentation-models-pytorch"' in lock
    assert 'version = "0.5.0"' in lock
    assert 'name = "torch"' in lock
    assert 'version = "2.13.0"' in lock
    assert 'name = "torchvision"' in lock
    assert 'version = "0.28.0"' in lock


def test_bundled_model_run_schema_matches_shared_contract() -> None:
    bundled = json.loads(
        files("geoai_runner").joinpath("schemas/model-run.schema.json").read_text(encoding="utf-8")
    )
    assert bundled == _shared_model_schema()


def _shared_model_schema() -> dict[str, object]:
    root = Path(__file__).resolve().parents[3]
    return json.loads(
        (root / "packages" / "contracts" / "schemas" / "model-run.schema.json").read_text(
            encoding="utf-8"
        )
    )


def _contains_private_path(payload: dict[str, object]) -> bool:
    serialized = json.dumps(payload, ensure_ascii=False)
    return any(
        marker in serialized for marker in ("C:\\\\", "C:/Users/", "/home/", "/Users/", "file://")
    )
