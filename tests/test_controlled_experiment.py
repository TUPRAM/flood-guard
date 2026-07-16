from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import floodguard.controlled_experiment as controlled
from floodguard.controlled_experiment import (
    ACQUISITION_COLUMNS,
    ACQUISITION_SCHEMA,
    CELL_GRID_COLUMNS,
    MODEL_CONTRACT_SCHEMAS,
    MODEL_EVIDENCE_COLUMNS,
    REQUIRED_MODEL_FAMILIES,
    ZERO_DIVISION_CONVENTION,
    ControlledExperimentError,
    VerifiedSpatialHoldout,
    assess_acquisition_manifest,
    build_gate_receipt,
    build_gate_report_markdown,
    compare_three_model_predictions,
    freeze_spatial_holdout,
    load_signed_reference_cell_evidence,
    load_spatial_holdout,
    run_controlled_three_model_experiment,
    write_acquisition_authority_receipt,
    write_gate_report,
    write_signed_reference_cell_receipt,
    write_signed_model_run_manifest,
)


UTC = timezone.utc
SHA_A = "a" * 64
SHA_B = "b" * 64
KEY_ID = "test-authority-v1"
SIGNING_KEY = b"floodguard-test-signing-key-32-bytes-minimum"
SIGNING_KEYS = {KEY_ID: SIGNING_KEY}


def test_editable_acquisition_csv_cannot_self_authorize(tmp_path: Path) -> None:
    manifest, artifacts = _acquisition_fixture(tmp_path, base_ready=True)

    assessment = assess_acquisition_manifest(manifest, artifact_paths=artifacts)

    assert assessment.ready is False
    assert assessment.authority_receipt_sha256 is None
    assert assessment.blockers == (
        "acquisition_authority: signed catalog/license allowlist receipt is missing",
    )


def test_signed_acquisition_authority_binds_products_permissions_and_bytes(
    tmp_path: Path,
) -> None:
    manifest, artifacts, authority, assessment = _authorized_acquisition(tmp_path)

    assert assessment.ready is True
    assert assessment.blockers == ()
    assert assessment.authority_receipt_sha256 == _sha(authority)
    assert set(dict(assessment.sha256_by_role)) == {
        "pre_event_sar",
        "post_event_sar",
        "reference_mask",
    }

    payload = json.loads(authority.read_text(encoding="utf-8"))
    payload["authorizations"][0]["product_id"] = "SUBSTITUTED"
    authority.write_text(json.dumps(payload), encoding="utf-8")
    blocked = assess_acquisition_manifest(
        manifest,
        artifact_paths=artifacts,
        authority_receipt_path=authority,
        signing_keys=SIGNING_KEYS,
        verified_at_utc=datetime(2024, 1, 5, tzinfo=UTC),
    )
    assert blocked.ready is False
    assert any("HMAC signature is invalid" in item for item in blocked.blockers)


def test_acquisition_byte_substitution_and_unresolved_truth_fail_closed(
    tmp_path: Path,
) -> None:
    manifest, artifacts = _acquisition_fixture(tmp_path / "bytes", base_ready=True)
    artifacts["post_event_sar"].write_bytes(b"substituted")
    with pytest.raises(ControlledExperimentError, match="attempts to override"):
        assess_acquisition_manifest(manifest, artifact_paths=artifacts)

    manifest, artifacts = _acquisition_fixture(
        tmp_path / "truth",
        base_ready=False,
    )
    base = assess_acquisition_manifest(manifest, artifact_paths=artifacts)
    with pytest.raises(ControlledExperimentError, match="base gates are blocked"):
        _issue_authority(tmp_path / "truth", manifest, base)


def test_acquisition_rejects_private_path_and_invalid_authority_key(
    tmp_path: Path,
) -> None:
    manifest, artifacts, authority, _assessment = _authorized_acquisition(tmp_path)
    frame = pd.read_csv(manifest)
    frame.loc[frame["role"].eq("reference_mask"), "local_path_hint"] = (
        r"C:\private\mask.tif"
    )
    frame.to_csv(manifest, index=False, lineterminator="\n")
    with pytest.raises(ControlledExperimentError, match="redacted"):
        assess_acquisition_manifest(manifest, artifact_paths=artifacts)

    manifest, artifacts, authority, _assessment = _authorized_acquisition(
        tmp_path / "wrong-key"
    )
    blocked = assess_acquisition_manifest(
        manifest,
        artifact_paths=artifacts,
        authority_receipt_path=authority,
        signing_keys={"other": SIGNING_KEY},
        verified_at_utc=datetime(2024, 1, 5, tzinfo=UTC),
    )
    assert blocked.ready is False
    assert any("not trusted at runtime" in item for item in blocked.blockers)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("product_id", "", "product_id must not be blank"),
        ("product_id", "unsafe/product", "stable product identifier"),
        ("source_name", " ", "source_name must not be blank"),
        ("assumptions", "", "assumptions must not be blank"),
        ("acquisition_start_utc", "not-a-time", "must be ISO-8601"),
        ("acquisition_end_utc", "2024-01-02T00:01:00", "must include a timezone"),
        ("source_timestamp", "", "source_timestamp must not be blank"),
        ("source_timestamp", "2024-01-01T00:00:00Z", "outside the acquisition"),
    ],
)
def test_acquisition_rejects_missing_or_malformed_identity_and_timestamps(
    tmp_path: Path,
    field: str,
    value: str,
    message: str,
) -> None:
    manifest, artifacts = _acquisition_fixture(tmp_path, base_ready=True)
    frame = pd.read_csv(manifest)
    frame.loc[frame["role"].eq("post_event_sar"), field] = value
    frame.to_csv(manifest, index=False, lineterminator="\n")

    with pytest.raises(ControlledExperimentError, match=message):
        assess_acquisition_manifest(manifest, artifact_paths=artifacts)


def test_acquisition_authority_binds_source_identity_and_all_timestamps(
    tmp_path: Path,
) -> None:
    manifest, artifacts, authority, _assessment = _authorized_acquisition(tmp_path)
    original_authority_sha = _sha(authority)
    frame = pd.read_csv(manifest)
    frame.loc[frame["role"].eq("post_event_sar"), "source_timestamp"] = (
        "2024-01-02T00:00:30Z"
    )
    frame.to_csv(manifest, index=False, lineterminator="\n")

    blocked = assess_acquisition_manifest(
        manifest,
        artifact_paths=artifacts,
        authority_receipt_path=authority,
        signing_keys=SIGNING_KEYS,
        verified_at_utc=datetime(2024, 1, 5, tzinfo=UTC),
    )
    assert blocked.ready is False
    assert blocked.authority_receipt_sha256 is None
    assert any(
        "authority manifest was substituted" in item for item in blocked.blockers
    )
    assert _sha(authority) == original_authority_sha


def test_acquisition_authority_preserves_and_binds_subsecond_timestamps(
    tmp_path: Path,
) -> None:
    manifest, artifacts = _acquisition_fixture(tmp_path, base_ready=True)
    frame = pd.read_csv(manifest)
    post = frame["role"].eq("post_event_sar")
    frame.loc[post, "acquisition_start_utc"] = "2024-01-02T00:00:00.123456Z"
    frame.loc[post, "acquisition_end_utc"] = "2024-01-02T00:01:00.123456Z"
    frame.loc[post, "source_timestamp"] = "2024-01-02T00:00:00.123456Z"
    frame.to_csv(manifest, index=False, lineterminator="\n")
    base = assess_acquisition_manifest(manifest, artifact_paths=artifacts)
    authority = _issue_authority(tmp_path, manifest, base)

    payload = json.loads(authority.read_text(encoding="utf-8"))
    authorization = next(
        row for row in payload["authorizations"] if row["role"] == "post_event_sar"
    )
    assert authorization["acquisition_start_utc"].endswith(".123456Z")
    assert authorization["acquisition_end_utc"].endswith(".123456Z")
    assert authorization["source_timestamp"].endswith(".123456Z")

    frame.loc[post, "source_timestamp"] = "2024-01-02T00:00:00.654321Z"
    frame.to_csv(manifest, index=False, lineterminator="\n")
    blocked = assess_acquisition_manifest(
        manifest,
        artifact_paths=artifacts,
        authority_receipt_path=authority,
        signing_keys=SIGNING_KEYS,
        verified_at_utc=datetime(2024, 1, 5, tzinfo=UTC),
    )
    assert blocked.ready is False
    assert any(
        "authority manifest was substituted" in item for item in blocked.blockers
    )


def test_authority_hash_and_parser_use_one_exact_byte_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, artifacts, authority, _assessment = _authorized_acquisition(tmp_path)
    original = authority.read_bytes()
    original_sha = hashlib.sha256(original).hexdigest()
    alternate = json.dumps({"substituted": True}).encode()
    parse = controlled._json_object_bytes

    def swap_after_snapshot(content: bytes, label: str) -> dict[str, object]:
        payload = parse(content, label)
        if label == "acquisition authority receipt":
            authority.write_bytes(alternate)
        return payload

    monkeypatch.setattr(controlled, "_json_object_bytes", swap_after_snapshot)
    assessment = assess_acquisition_manifest(
        manifest,
        artifact_paths=artifacts,
        authority_receipt_path=authority,
        signing_keys=SIGNING_KEYS,
        verified_at_utc=datetime(2024, 1, 5, tzinfo=UTC),
    )
    assert assessment.ready is True
    assert assessment.authority_receipt_sha256 == original_sha
    assert authority.read_bytes() == alternate
    authority.write_bytes(original)


def test_descriptor_snapshot_rejects_detected_mid_read_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "receipt.json"
    target.write_bytes(b'{"original":true}\n')
    original_open = controlled._open_stable_binary

    class MutatingReader:
        def __init__(self, stream: object) -> None:
            self.stream = stream

        def fileno(self) -> int:
            return self.stream.fileno()

        def read(self, *args: object) -> bytes:
            content = self.stream.read(*args)
            target.write_bytes(b'{"mutated":true,"longer":true}\n')
            return content

    @contextmanager
    def attacked_open(path: Path, label: str):
        with original_open(path, label) as stream:
            yield MutatingReader(stream)

    monkeypatch.setattr(controlled, "_open_stable_binary", attacked_open)
    with pytest.raises(
        ControlledExperimentError, match="changed while its bytes were read"
    ):
        controlled._read_stable_bytes(target, "test receipt")


def test_holdout_signature_membership_and_geometry_are_all_bound(
    tmp_path: Path,
) -> None:
    holdout, geometry, grid_contract, membership, receipt = _holdout_fixture(tmp_path)

    loaded = load_spatial_holdout(
        receipt,
        geometry,
        grid_contract,
        membership,
        signing_keys=SIGNING_KEYS,
    )
    assert loaded == holdout
    assert [item.cell_id for item in loaded.memberships] == ["C1", "C2", "C3", "C4"]
    assert loaded.receipt["cell_area_m2"] == 2500.0

    with pytest.raises(ControlledExperimentError, match="not trusted at runtime"):
        load_spatial_holdout(
            receipt,
            geometry,
            grid_contract,
            membership,
            signing_keys={"wrong": SIGNING_KEY},
        )

    membership_bytes = membership.read_bytes()
    membership_frame = pd.read_csv(membership)
    membership_frame.loc[membership_frame["cell_id"].eq("C3"), "split"] = "train"
    membership_frame.to_csv(membership, index=False, lineterminator="\n")
    with pytest.raises(ControlledExperimentError, match="membership SHA-256"):
        load_spatial_holdout(
            receipt,
            geometry,
            grid_contract,
            membership,
            signing_keys=SIGNING_KEYS,
        )
    membership.write_bytes(membership_bytes)

    payload = json.loads(geometry.read_text(encoding="utf-8"))
    payload["features"][1]["geometry"]["coordinates"][0][1][0] = 300
    geometry.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ControlledExperimentError, match="SHA-256"):
        load_spatial_holdout(
            receipt,
            geometry,
            grid_contract,
            membership,
            signing_keys=SIGNING_KEYS,
        )


def test_holdout_rejects_non_equal_area_crs_overlap_and_outside_cells(
    tmp_path: Path,
) -> None:
    geometry = _holdout_geojson(tmp_path / "crs")
    grid = _cell_grid(tmp_path / "crs")
    with pytest.raises(ControlledExperimentError, match="equal-area"):
        freeze_spatial_holdout(
            geometry,
            grid_contract_path=tmp_path / "crs" / "grid-contract.json",
            cell_grid_path=grid,
            membership_output_path=tmp_path / "crs" / "membership.csv",
            experiment_id="EXP-1",
            study_area="Test area",
            target_crs="EPSG:32647",
            grid_contract_sha256=_sha(tmp_path / "crs" / "grid-contract.json"),
            source_registry_sha256=SHA_B,
            frozen_at_utc=datetime(2024, 1, 1, tzinfo=UTC),
            assumptions="Synthetic contract fixture.",
            signing_key_id=KEY_ID,
            signing_key=SIGNING_KEY,
            output_path=tmp_path / "crs" / "receipt.json",
        )

    geometry = _holdout_geojson(tmp_path / "overlap")
    payload = json.loads(geometry.read_text(encoding="utf-8"))
    payload["features"][1]["geometry"]["coordinates"] = [
        [[50, 0], [150, 0], [150, 100], [50, 100], [50, 0]]
    ]
    geometry.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ControlledExperimentError, match="interiors overlap"):
        _freeze_paths(tmp_path / "overlap", geometry, _cell_grid(tmp_path / "overlap"))

    geometry = _holdout_geojson(tmp_path / "outside")
    payload = json.loads(geometry.read_text(encoding="utf-8"))
    payload["features"][1]["geometry"]["coordinates"] = [
        [[100, 0], [150, 0], [150, 100], [100, 100], [100, 0]]
    ]
    geometry.write_text(json.dumps(payload), encoding="utf-8")
    grid = _cell_grid(tmp_path / "outside")
    with pytest.raises(ControlledExperimentError, match="outside all polygons"):
        _freeze_paths(tmp_path / "outside", geometry, grid)


def test_grid_area_is_affine_derived_and_substitutions_fail_closed(
    tmp_path: Path,
) -> None:
    geometry = _holdout_geojson(tmp_path)
    grid = _cell_grid(tmp_path)
    frame = pd.read_csv(grid)
    frame["cell_area_m2"] = 999999.0
    frame.to_csv(grid, index=False, lineterminator="\n")
    with pytest.raises(ControlledExperimentError, match="affine determinant"):
        _freeze_paths(tmp_path, geometry, grid)

    frame["cell_area_m2"] = 2500.0
    frame.to_csv(grid, index=False, lineterminator="\n")
    holdout = _freeze_paths(tmp_path, geometry, grid)
    assert holdout.receipt["cell_area_m2"] == 2500.0

    contract_path = tmp_path / "grid-contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["transform"][0] = 100.0
    contract_path.write_text(json.dumps(contract, sort_keys=True), encoding="utf-8")
    with pytest.raises(ControlledExperimentError, match="Grid contract SHA-256"):
        load_spatial_holdout(
            tmp_path / "holdout-receipt.json",
            geometry,
            contract_path,
            tmp_path / "membership.csv",
            signing_keys=SIGNING_KEYS,
        )


def test_grid_contract_requires_exact_membership_and_affine_centers(
    tmp_path: Path,
) -> None:
    geometry = _holdout_geojson(tmp_path)
    grid = _cell_grid(tmp_path)
    frame = pd.read_csv(grid)
    frame.loc[frame["cell_id"].eq("C4"), "x"] = 176.0
    frame.to_csv(grid, index=False, lineterminator="\n")
    with pytest.raises(ControlledExperimentError, match="affine-derived cell centers"):
        _freeze_paths(tmp_path, geometry, grid)

    frame = frame.loc[~frame["cell_id"].eq("C4")].copy()
    frame.loc[frame["cell_id"].eq("C3"), "x"] = 125.0
    frame.to_csv(grid, index=False, lineterminator="\n")
    with pytest.raises(ControlledExperimentError, match="exactly cover"):
        _freeze_paths(tmp_path, geometry, grid)


def test_comparison_uses_frozen_membership_and_physical_area(tmp_path: Path) -> None:
    holdout, reference = _comparison_fixture(tmp_path)

    metrics, calibration, errors = compare_three_model_predictions(
        _prediction_frames(),
        holdout,
        reference_cells=reference,
        thresholds=_thresholds(),
        calibration_bins=4,
    )

    assert set(metrics["model_family"]) == set(REQUIRED_MODEL_FAMILIES)
    assert {
        "iou",
        "f1_dice",
        "precision",
        "recall",
        "predicted_area_m2",
        "reference_area_m2",
        "area_error_m2",
        "absolute_area_error_m2",
        "area_error_ratio",
        "brier_score",
        "expected_calibration_error",
    }.issubset(metrics.columns)
    deterministic = metrics.set_index("model_family").loc["deterministic_sar_baseline"]
    assert deterministic["predicted_area_m2"] == 5000.0
    assert deterministic["reference_area_m2"] == 2500.0
    assert deterministic["area_error_m2"] == 2500.0
    assert deterministic["area_error_ratio"] == 1.0
    assert len(calibration) == 12
    assert set(errors["category"]) == {
        "all",
        "permanent_water",
        "radar_shadow",
        "steep_terrain",
        "urban_surface",
    }
    assert not metrics["can_feed_decision_layer"].any()


def test_comparison_rejects_relabel_missing_cell_and_reference_substitution(
    tmp_path: Path,
) -> None:
    holdout, reference = _comparison_fixture(tmp_path)
    predictions = _prediction_frames()
    predictions["weak_label_logistic"].loc[2, "split"] = "train"
    with pytest.raises(ControlledExperimentError, match="relabelled"):
        compare_three_model_predictions(
            predictions,
            holdout,
            reference_cells=reference,
            thresholds=_thresholds(),
        )

    predictions = _prediction_frames()
    predictions["geoai_candidate"] = predictions["geoai_candidate"].iloc[:-1]
    with pytest.raises(ControlledExperimentError, match="frozen membership"):
        compare_three_model_predictions(
            predictions,
            holdout,
            reference_cells=reference,
            thresholds=_thresholds(),
        )

    predictions = _prediction_frames()
    predictions["geoai_candidate"]["reference_flood_extent"] = [0, 1, 1, 0]
    with pytest.raises(ControlledExperimentError, match="columns do not match"):
        compare_three_model_predictions(
            predictions,
            holdout,
            reference_cells=reference,
            thresholds=_thresholds(),
        )


def test_zero_division_convention_is_finite_and_documented(tmp_path: Path) -> None:
    dry_reference = _reference_frame()
    dry_reference["reference_flood_extent"] = 0
    holdout, reference = _comparison_fixture(tmp_path, reference_frame=dry_reference)
    predictions = _prediction_frames()
    for frame in predictions.values():
        frame["probability_0_1"] = 0.0

    metrics, _calibration, _errors = compare_three_model_predictions(
        predictions,
        holdout,
        reference_cells=reference,
        thresholds=_thresholds(),
    )

    numeric = metrics.select_dtypes(include="number")
    assert numeric.map(math.isfinite).all().all()
    assert metrics["iou"].eq(0.0).all()
    assert metrics["precision"].eq(0.0).all()
    assert metrics["recall"].eq(0.0).all()
    assert metrics["area_error_ratio"].eq(0.0).all()
    assert ZERO_DIVISION_CONVENTION.startswith("finite:")


def test_signed_reference_cells_reject_substitution_wrong_key_and_lineage(
    tmp_path: Path,
) -> None:
    _manifest, _artifacts, _authority, acquisition = _authorized_acquisition(
        tmp_path / "acquisition"
    )
    holdout, _geometry, _grid, _membership, _holdout_receipt = _holdout_fixture(
        tmp_path / "holdout"
    )
    reference, evidence_path, receipt_path = _reference_fixture(
        tmp_path / "reference", acquisition, holdout
    )

    assert len(reference.cells) == len(holdout.memberships)
    assert reference.reference_mask_sha256 == acquisition.reference_mask_sha256

    original = evidence_path.read_bytes()
    substituted = pd.read_csv(evidence_path)
    substituted.loc[substituted["cell_id"].eq("C3"), "reference_flood_extent"] = 1
    substituted.to_csv(evidence_path, index=False, lineterminator="\n")
    with pytest.raises(ControlledExperimentError, match="checksum was substituted"):
        load_signed_reference_cell_evidence(
            receipt_path,
            evidence_path,
            acquisition=acquisition,
            holdout=holdout,
            signing_keys=SIGNING_KEYS,
        )
    evidence_path.write_bytes(original)

    with pytest.raises(ControlledExperimentError, match="not trusted at runtime"):
        load_signed_reference_cell_evidence(
            receipt_path,
            evidence_path,
            acquisition=acquisition,
            holdout=holdout,
            signing_keys={"wrong-key": SIGNING_KEY},
        )

    altered_roles = tuple(
        (role, SHA_B if role == "reference_mask" else digest)
        for role, digest in acquisition.sha256_by_role
    )
    altered_acquisition = replace(acquisition, sha256_by_role=altered_roles)
    with pytest.raises(ControlledExperimentError, match="reference_mask_sha256"):
        load_signed_reference_cell_evidence(
            receipt_path,
            evidence_path,
            acquisition=altered_acquisition,
            holdout=holdout,
            signing_keys=SIGNING_KEYS,
        )


def test_gate_receipt_stays_blocked_without_signed_authority_human_or_models(
    tmp_path: Path,
) -> None:
    manifest, artifacts = _acquisition_fixture(tmp_path, base_ready=False)
    acquisition = assess_acquisition_manifest(manifest, artifact_paths=artifacts)
    receipt = build_gate_receipt(
        acquisition,
        generated_at_utc=datetime(2026, 7, 16, tzinfo=UTC),
    )

    assert receipt["gate_status"] == "blocked"
    assert receipt["processing_allowed"] is False
    assert receipt["experiment_executed"] is False
    assert receipt["official_warning"] is False
    assert "C:\\" not in json.dumps(receipt)
    assert any("reviewer_calibration" in item for item in receipt["blockers"])
    assert any("acquisition_authority" in item for item in receipt["blockers"])

    outputs = write_gate_report(
        receipt,
        manifest,
        json_output_path=tmp_path / "gate.json",
        markdown_output_path=tmp_path / "gate.md",
    )
    report = outputs["report"].read_text(encoding="utf-8")
    assert "No real training" in report
    assert "editable CSV claims are not authority" in report


def test_full_runner_verifies_signed_artifacts_runs_and_thresholds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _runner_fixture(tmp_path, monkeypatch)

    outputs = _run_fixture(fixture, tmp_path / "results")

    result = json.loads(outputs["receipt"].read_text(encoding="utf-8"))
    assert result["comparison_status"] == "completed_report_only"
    assert result["can_feed_decision_layer"] is False
    assert result["official_warning"] is False
    assert result["zero_division_convention"] == ZERO_DIVISION_CONVENTION
    assert result["reference_cell_receipt_file_sha256"] == _sha(
        fixture["reference_receipt"]
    )
    assert result["reference_cell_evidence_sha256"] == _sha(
        fixture["reference_evidence"]
    )
    assert len(result["models"]) == 3
    assert {row["model_contract_schema"] for row in result["models"]} == set(
        MODEL_CONTRACT_SCHEMAS.values()
    )
    assert all(row["model_contract_file_sha256"] for row in result["models"])
    assert all(row["model_contract_sha256"] for row in result["models"])
    assert {row["floodguard_commit"] for row in result["models"]} == {"d" * 40}
    assert pd.read_csv(outputs["metrics"]).shape[0] == 3


def test_full_runner_rejects_model_artifact_and_run_manifest_substitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _runner_fixture(tmp_path / "artifact", monkeypatch)
    family = "geoai_candidate"
    fixture["model_artifacts"][family].write_bytes(b"substituted artifact")
    evidence = pd.read_csv(fixture["model_evidence"])
    evidence.loc[evidence["model_family"].eq(family), "model_artifact_sha256"] = _sha(
        fixture["model_artifacts"][family]
    )
    evidence.to_csv(fixture["model_evidence"], index=False, lineterminator="\n")
    with pytest.raises(ControlledExperimentError, match="model artifact"):
        _run_fixture(fixture, tmp_path / "artifact-results")

    fixture = _runner_fixture(tmp_path / "run", monkeypatch)
    family = "weak_label_logistic"
    run_path = fixture["model_runs"][family]
    run = json.loads(run_path.read_text(encoding="utf-8"))
    run["decision_threshold"] = 0.99
    run_path.write_text(json.dumps(run), encoding="utf-8")
    evidence = pd.read_csv(fixture["model_evidence"])
    evidence.loc[evidence["model_family"].eq(family), "model_run_manifest_sha256"] = (
        _sha(run_path)
    )
    evidence.to_csv(fixture["model_evidence"], index=False, lineterminator="\n")
    with pytest.raises(ControlledExperimentError, match="HMAC signature is invalid"):
        _run_fixture(fixture, tmp_path / "run-results")


@pytest.mark.parametrize(
    ("family", "field_path", "value", "message"),
    [
        (
            "deterministic_sar_baseline",
            ("lane", "algorithm"),
            "neural_net",
            "algorithm",
        ),
        (
            "weak_label_logistic",
            ("lane", "preprocessing"),
            "global_fit",
            "preprocessing",
        ),
        ("geoai_candidate", ("lane", "architecture"), "transformer", "architecture"),
        ("geoai_candidate", ("lane", "encoder_weights"), "imagenet", "encoder_weights"),
        ("geoai_candidate", ("lane", "geoai_commit"), "0" * 40, "source commit"),
        (
            "geoai_candidate",
            ("lane", "preprocessing", "method"),
            "implicit_divide_255",
            "explicitly encode",
        ),
        ("geoai_candidate", ("floodguard_commit",), "short", "FloodGuard commit"),
    ],
)
def test_lane_contracts_reject_wrong_family_configuration(
    tmp_path: Path,
    family: str,
    field_path: tuple[str, ...],
    value: object,
    message: str,
) -> None:
    artifact = tmp_path / f"{family}.bin"
    artifact.write_bytes(b"model")
    model_id = "MODEL-TEST"
    contract_path = _model_lane_contract(tmp_path, family, model_id, artifact)
    payload = json.loads(contract_path.read_text(encoding="utf-8"))
    target = payload
    for field in field_path[:-1]:
        target = target[field]
    target[field_path[-1]] = value
    contract_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    with pytest.raises(ControlledExperimentError, match=message):
        controlled._load_model_lane_contract(
            contract_path,
            family=family,
            model_id=model_id,
            model_artifact_sha256=_sha(artifact),
        )


def test_full_runner_rejects_coordinated_lane_contract_substitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _runner_fixture(tmp_path, monkeypatch)
    family = "geoai_candidate"
    contract_path = fixture["model_contracts"][family]
    payload = json.loads(contract_path.read_text(encoding="utf-8"))
    payload["lane"]["architecture"] = "fpn"
    contract_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    evidence = pd.read_csv(fixture["model_evidence"])
    mask = evidence["model_family"].eq(family)
    evidence.loc[mask, "model_contract_file_sha256"] = _sha(contract_path)
    evidence.loc[mask, "model_contract_sha256"] = controlled._canonical_sha256(payload)
    evidence.to_csv(fixture["model_evidence"], index=False, lineterminator="\n")

    with pytest.raises(ControlledExperimentError, match="signed lane contract"):
        _run_fixture(fixture, tmp_path / "results")


def test_full_runner_rejects_coordinated_all_prediction_substitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _runner_fixture(tmp_path, monkeypatch)
    evidence = pd.read_csv(fixture["model_evidence"])
    for family, prediction_path in fixture["predictions"].items():
        prediction = pd.read_csv(prediction_path)
        prediction["probability_0_1"] = 0.99
        prediction.to_csv(prediction_path, index=False, lineterminator="\n")
        evidence.loc[evidence["model_family"].eq(family), "prediction_sha256"] = _sha(
            prediction_path
        )
    evidence.to_csv(fixture["model_evidence"], index=False, lineterminator="\n")

    with pytest.raises(
        ControlledExperimentError, match="signed prediction was substituted"
    ):
        _run_fixture(fixture, tmp_path / "results")


def test_signed_run_rejects_wrong_contract_and_editable_threshold_column(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _runner_fixture(tmp_path / "contract", monkeypatch)
    family = "deterministic_sar_baseline"
    run_path = fixture["model_runs"][family]
    run = json.loads(run_path.read_text(encoding="utf-8"))
    unsigned = {
        key: value
        for key, value in run.items()
        if key not in {"manifest_sha256", "signature"}
    }
    unsigned["model_contract_schema"] = "floodguard.wrong_contract.v1"
    resealed = controlled._seal_signed_payload(
        unsigned,
        signing_key_id=KEY_ID,
        signing_key=SIGNING_KEY,
        self_hash_field="manifest_sha256",
    )
    run_path.write_text(json.dumps(resealed), encoding="utf-8")
    evidence = pd.read_csv(fixture["model_evidence"])
    evidence.loc[evidence["model_family"].eq(family), "model_run_manifest_sha256"] = (
        _sha(run_path)
    )
    evidence.to_csv(fixture["model_evidence"], index=False, lineterminator="\n")
    with pytest.raises(ControlledExperimentError, match="contract schema mismatch"):
        _run_fixture(fixture, tmp_path / "contract-results")

    fixture = _runner_fixture(tmp_path / "editable", monkeypatch)
    evidence = pd.read_csv(fixture["model_evidence"])
    evidence["decision_threshold"] = 0.01
    evidence.to_csv(fixture["model_evidence"], index=False, lineterminator="\n")
    with pytest.raises(ControlledExperimentError, match="extra=.*decision_threshold"):
        _run_fixture(fixture, tmp_path / "editable-results")


def test_committed_blocked_report_and_no_root_geoai_import() -> None:
    root = Path(__file__).resolve().parents[1]
    receipt = json.loads(
        (root / "docs/validation/controlled_three_model_gate_receipt.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = pd.read_csv(
        root / "docs/validation/controlled_three_model_acquisition_manifest.csv"
    )
    report = build_gate_report_markdown(receipt, manifest)
    assert receipt["gate_status"] == "blocked"
    assert "No real training" in report
    assert any("acquisition_authority" in item for item in receipt["blockers"])
    assert "import geoai" not in (
        root / "src/floodguard/controlled_experiment.py"
    ).read_text(encoding="utf-8")


def _acquisition_fixture(
    tmp_path: Path,
    *,
    base_ready: bool,
) -> tuple[Path, dict[str, Path]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    contents = {
        "pre_event_sar": b"pre",
        "post_event_sar": b"post",
        "reference_mask": b"mask",
    }
    artifacts: dict[str, Path] = {}
    for role, content in contents.items():
        path = tmp_path / f"{role}.bin"
        path.write_bytes(content)
        artifacts[role] = path
    times = {
        "pre_event_sar": ("2023-12-31T00:00:00Z", "2023-12-31T00:01:00Z"),
        "post_event_sar": ("2024-01-02T00:00:00Z", "2024-01-02T00:01:00Z"),
        "reference_mask": ("2024-01-02T00:00:00Z", "2024-01-02T23:59:59Z"),
    }
    rows = []
    for role in contents:
        is_reference = role == "reference_mask"
        row_ready = base_ready or not is_reference
        start, end = times[role]
        rows.append(
            {
                "schema_version": ACQUISITION_SCHEMA,
                "experiment_id": "EXP-1",
                "study_area": "Test area",
                "role": role,
                "source_name": f"Source {role}",
                "source_url": f"https://example.test/{role}",
                "product_id": f"PRODUCT-{role}",
                "acquisition_start_utc": start,
                "acquisition_end_utc": end,
                "local_path_hint": (
                    f"<external_data_workspace>/{artifacts[role].name}"
                ),
                "sha256": _sha(artifacts[role]),
                "sha256_status": "verified",
                "license_status": (
                    "confirmed_for_experiment" if row_ready else "unresolved"
                ),
                "local_analysis_allowed": row_ready,
                "derived_metrics_allowed": row_ready,
                "ml_label_use_allowed": row_ready,
                "redistribution_status": (
                    "reference_only" if row_ready else "unresolved"
                ),
                "reference_mask_status": (
                    "qualified_expert_or_adjudicated"
                    if is_reference and row_ready
                    else "candidate_not_qualified"
                    if is_reference
                    else "not_applicable"
                ),
                "temporal_alignment_status": (
                    "confirmed" if row_ready else "unresolved"
                ),
                "processing_allowed": row_ready,
                "source_timestamp": end,
                "assumptions": "Synthetic test fixture.",
            }
        )
    manifest = tmp_path / "acquisition.csv"
    pd.DataFrame(rows, columns=ACQUISITION_COLUMNS).to_csv(
        manifest,
        index=False,
        lineterminator="\n",
    )
    return manifest, artifacts


def _issue_authority(
    tmp_path: Path,
    manifest: Path,
    base: controlled.AcquisitionGateAssessment,
) -> Path:
    authority = tmp_path / "acquisition-authority.json"
    write_acquisition_authority_receipt(
        base,
        manifest,
        authority_id="TEST-DATA-CUSTODIAN",
        allowlist_id="TEST-ALLOWLIST-1",
        catalog_receipt_sha256_by_role={
            role: hashlib.sha256(f"catalog-{role}".encode()).hexdigest()
            for role in contents_roles()
        },
        license_receipt_sha256_by_role={
            role: hashlib.sha256(f"license-{role}".encode()).hexdigest()
            for role in contents_roles()
        },
        issued_at_utc=datetime(2023, 12, 1, tzinfo=UTC),
        expires_at_utc=datetime(2030, 1, 1, tzinfo=UTC),
        signing_key_id=KEY_ID,
        signing_key=SIGNING_KEY,
        output_path=authority,
    )
    return authority


def _authorized_acquisition(
    tmp_path: Path,
) -> tuple[Path, dict[str, Path], Path, controlled.AcquisitionGateAssessment]:
    manifest, artifacts = _acquisition_fixture(tmp_path, base_ready=True)
    base = assess_acquisition_manifest(manifest, artifact_paths=artifacts)
    authority = _issue_authority(tmp_path, manifest, base)
    assessment = assess_acquisition_manifest(
        manifest,
        artifact_paths=artifacts,
        authority_receipt_path=authority,
        signing_keys=SIGNING_KEYS,
        verified_at_utc=datetime(2024, 1, 5, tzinfo=UTC),
    )
    return manifest, artifacts, authority, assessment


def contents_roles() -> tuple[str, str, str]:
    return ("pre_event_sar", "post_event_sar", "reference_mask")


def _holdout_geojson(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    payload = {
        "type": "FeatureCollection",
        "floodguard_crs": "EPSG:6933",
        "features": [
            {
                "type": "Feature",
                "properties": {"spatial_group_id": "TRAIN-A", "split": "train"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]]],
                },
            },
            {
                "type": "Feature",
                "properties": {
                    "spatial_group_id": "HOLDOUT-B",
                    "split": "holdout",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[100, 0], [200, 0], [200, 100], [100, 100], [100, 0]]
                    ],
                },
            },
        ],
    }
    path = tmp_path / "holdout.geojson"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _cell_grid(tmp_path: Path, *, outside: bool = False) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    contract = _grid_contract(tmp_path)
    x_values = [25.0, 75.0, 125.0, 250.0 if outside else 175.0]
    frame = pd.DataFrame(
        {
            "cell_id": ["C1", "C2", "C3", "C4"],
            "x": x_values,
            "y": [50.0] * 4,
            "row_index": [0] * 4,
            "column_index": [0, 1, 2, 3],
            "cell_area_m2": [2500.0] * 4,
            "grid_contract_sha256": [_sha(contract)] * 4,
        },
        columns=CELL_GRID_COLUMNS,
    )
    path = tmp_path / "cells.csv"
    frame.to_csv(path, index=False, lineterminator="\n")
    return path


def _grid_contract(tmp_path: Path) -> Path:
    path = tmp_path / "grid-contract.json"
    if path.exists():
        return path
    payload = {
        "artifact_schema": controlled.GRID_CONTRACT_SCHEMA,
        "grid_id": "TEST-GRID-1",
        "target_crs": "EPSG:6933",
        "transform": [50.0, 0.0, 0.0, 0.0, -50.0, 75.0],
        "width": 4,
        "height": 1,
        "cell_ids_sha256": controlled._canonical_sha256(["C1", "C2", "C3", "C4"]),
        "source_grid_sha256": hashlib.sha256(b"synthetic-grid-source").hexdigest(),
        "created_at_utc": "2023-12-31T00:00:00Z",
        "official_warning": False,
    }
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _freeze_paths(
    tmp_path: Path,
    geometry: Path,
    grid: Path,
) -> VerifiedSpatialHoldout:
    return freeze_spatial_holdout(
        geometry,
        grid_contract_path=grid.with_name("grid-contract.json"),
        cell_grid_path=grid,
        membership_output_path=tmp_path / "membership.csv",
        experiment_id="EXP-1",
        study_area="Test area",
        target_crs="EPSG:6933",
        grid_contract_sha256=_sha(grid.with_name("grid-contract.json")),
        source_registry_sha256=SHA_B,
        frozen_at_utc=datetime(2024, 1, 1, tzinfo=UTC),
        assumptions="Synthetic contract fixture.",
        signing_key_id=KEY_ID,
        signing_key=SIGNING_KEY,
        output_path=tmp_path / "holdout-receipt.json",
    )


def _holdout_fixture(
    tmp_path: Path,
) -> tuple[VerifiedSpatialHoldout, Path, Path, Path, Path]:
    geometry = _holdout_geojson(tmp_path)
    grid = _cell_grid(tmp_path)
    holdout = _freeze_paths(tmp_path, geometry, grid)
    return (
        holdout,
        geometry,
        tmp_path / "grid-contract.json",
        tmp_path / "membership.csv",
        tmp_path / "holdout-receipt.json",
    )


def _prediction_frames() -> dict[str, pd.DataFrame]:
    evidence = {
        "cell_id": ["C1", "C2", "C3", "C4"],
        "spatial_group_id": ["TRAIN-A", "TRAIN-A", "HOLDOUT-B", "HOLDOUT-B"],
        "split": ["train", "train", "holdout", "holdout"],
    }
    probabilities = {
        "deterministic_sar_baseline": [0.1, 0.8, 0.7, 0.6],
        "weak_label_logistic": [0.2, 0.7, 0.4, 0.8],
        "geoai_candidate": [0.1, 0.9, 0.2, 0.9],
    }
    return {
        family: pd.DataFrame({**evidence, "probability_0_1": values})
        for family, values in probabilities.items()
    }


def _reference_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cell_id": ["C1", "C2", "C3", "C4"],
            "reference_flood_extent": [0, 1, 0, 1],
            "permanent_water": [False, False, True, False],
            "radar_shadow": [False, True, False, False],
            "steep_terrain": [False, True, False, False],
            "urban_surface": [True, False, True, False],
        }
    )


def _reference_fixture(
    tmp_path: Path,
    acquisition: controlled.AcquisitionGateAssessment,
    holdout: VerifiedSpatialHoldout,
    *,
    frame: pd.DataFrame | None = None,
) -> tuple[controlled.VerifiedReferenceCellEvidence, Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    evidence_path = tmp_path / "reference-cells.csv"
    (frame if frame is not None else _reference_frame()).to_csv(
        evidence_path, index=False, lineterminator="\n"
    )
    receipt_path = tmp_path / "reference-cells-receipt.json"
    write_signed_reference_cell_receipt(
        evidence_path,
        acquisition=acquisition,
        holdout=holdout,
        derived_at_utc=datetime(2024, 1, 2, tzinfo=UTC),
        derivation_method="Synthetic qualified-mask fixture.",
        assumptions="Synthetic signed reference fixture.",
        signing_key_id=KEY_ID,
        signing_key=SIGNING_KEY,
        output_path=receipt_path,
    )
    verified = load_signed_reference_cell_evidence(
        receipt_path,
        evidence_path,
        acquisition=acquisition,
        holdout=holdout,
        signing_keys=SIGNING_KEYS,
    )
    return verified, evidence_path, receipt_path


def _comparison_fixture(
    tmp_path: Path,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> tuple[VerifiedSpatialHoldout, controlled.VerifiedReferenceCellEvidence]:
    _manifest, _artifacts, _authority, acquisition = _authorized_acquisition(
        tmp_path / "acquisition"
    )
    holdout, _geometry, _grid, _membership, _receipt = _holdout_fixture(
        tmp_path / "holdout"
    )
    reference, _evidence, _reference_receipt = _reference_fixture(
        tmp_path / "reference", acquisition, holdout, frame=reference_frame
    )
    return holdout, reference


def _thresholds() -> dict[str, float]:
    return {family: 0.5 for family in REQUIRED_MODEL_FAMILIES}


def _model_lane_contract(
    tmp_path: Path,
    family: str,
    model_id: str,
    artifact: Path,
) -> Path:
    common: dict[str, object] = {
        "artifact_schema": MODEL_CONTRACT_SCHEMAS[family],
        "model_family": family,
        "model_id": model_id,
        "model_artifact_sha256": _sha(artifact),
        "floodguard_commit": "d" * 40,
        "prediction_semantics": "binary_flood_probability_class_1",
    }
    if family == "deterministic_sar_baseline":
        lane: dict[str, object] = {
            "algorithm": "deterministic_sar_change_baseline",
            "feature_names": list(controlled.REQUIRED_SAR_CHANNELS),
            "configuration_sha256": hashlib.sha256(b"sar-config").hexdigest(),
            "split_policy": "immutable_spatial_holdout",
        }
    elif family == "weak_label_logistic":
        lane = {
            "algorithm": "logistic_regression",
            "feature_names": ["vv_change", "vh_change", "slope"],
            "preprocessing": "training_fold_only_standardization",
            "configuration_sha256": hashlib.sha256(b"logistic-config").hexdigest(),
            "split_policy": "grouped_spatial",
        }
    else:
        lane = {
            "geoai_version": controlled.EXPECTED_GEOAI_VERSION,
            "geoai_commit": controlled.EXPECTED_GEOAI_COMMIT,
            "architecture": "unet",
            "encoder": "resnet34",
            "encoder_weights": None,
            "channel_names": [
                *controlled.REQUIRED_SAR_CHANNELS,
                "slope",
                "permanent_water",
            ],
            "preprocessing": {
                "method": "fixed_clip_scale_to_uint8",
                "value_domain": "uint8_0_255",
                "sidecar_sha256": hashlib.sha256(b"preprocess-sidecar").hexdigest(),
            },
            "isolated_environment_manifest_sha256": hashlib.sha256(
                b"isolated-geoai-environment"
            ).hexdigest(),
            "run_contract_sha256": hashlib.sha256(
                b"typed-geoai-run-contract"
            ).hexdigest(),
        }
    path = tmp_path / f"{family}-lane-contract.json"
    path.write_text(
        json.dumps({**common, "lane": lane}, sort_keys=True), encoding="utf-8"
    )
    return path


def _runner_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    manifest, artifacts, authority, acquisition = _authorized_acquisition(tmp_path)
    holdout, geometry, grid_contract, membership, holdout_receipt = _holdout_fixture(
        tmp_path / "holdout"
    )
    reference, reference_evidence, reference_receipt = _reference_fixture(
        tmp_path / "reference", acquisition, holdout
    )
    reviewer_path = tmp_path / "reviewer.json"
    reviewer_path.write_text('{"synthetic_test_seam":true}\n', encoding="utf-8")
    reviewer_sha = _sha(reviewer_path)
    monkeypatch.setattr(
        controlled,
        "load_reviewer_calibration_receipt",
        lambda _path: SimpleNamespace(
            receipt_sha256="c" * 64,
            reviewer_ids=("A", "B"),
            formal_review_not_before_utc=datetime(2024, 1, 2, tzinfo=UTC),
        ),
    )
    prediction_paths: dict[str, Path] = {}
    model_artifacts: dict[str, Path] = {}
    model_contracts: dict[str, Path] = {}
    model_runs: dict[str, Path] = {}
    rows: list[dict[str, object]] = []
    for index, (family, frame) in enumerate(_prediction_frames().items()):
        prediction = tmp_path / f"{family}-predictions.csv"
        frame.to_csv(prediction, index=False, lineterminator="\n")
        prediction_paths[family] = prediction
        artifact = tmp_path / f"{family}-model.bin"
        artifact.write_bytes(f"model-{family}".encode())
        model_artifacts[family] = artifact
        model_id = f"MODEL-{index}"
        model_contract = _model_lane_contract(tmp_path, family, model_id, artifact)
        model_contracts[family] = model_contract
        run_path = tmp_path / f"{family}-run.json"
        write_signed_model_run_manifest(
            model_id=model_id,
            model_family=family,
            model_artifact_path=artifact,
            model_contract_path=model_contract,
            prediction_path=prediction,
            acquisition=acquisition,
            reviewer_calibration_file_sha256=reviewer_sha,
            holdout=holdout,
            reference_cells=reference,
            decision_threshold=0.5,
            threshold_selection_data_sha256=hashlib.sha256(
                f"training-data-{family}".encode()
            ).hexdigest(),
            threshold_selected_at_utc=datetime(2024, 1, 3, tzinfo=UTC),
            completed_at_utc=datetime(2024, 1, 4, tzinfo=UTC),
            assumptions="Synthetic signed run fixture.",
            signing_key_id=KEY_ID,
            signing_key=SIGNING_KEY,
            output_path=run_path,
        )
        model_runs[family] = run_path
        rows.append(
            {
                "model_id": model_id,
                "model_family": family,
                "prediction_file": prediction.name,
                "prediction_sha256": _sha(prediction),
                "model_artifact_file": artifact.name,
                "model_artifact_sha256": _sha(artifact),
                "model_contract_file": model_contract.name,
                "model_contract_file_sha256": _sha(model_contract),
                "model_contract_sha256": controlled._canonical_sha256(
                    json.loads(model_contract.read_text(encoding="utf-8"))
                ),
                "model_run_manifest_file": run_path.name,
                "model_run_manifest_sha256": _sha(run_path),
                "acquisition_manifest_sha256": acquisition.manifest_sha256,
                "reference_mask_sha256": acquisition.reference_mask_sha256,
                "spatial_holdout_manifest_sha256": holdout.manifest_sha256,
                "reviewer_calibration_file_sha256": reviewer_sha,
                "completed_at_utc": "2024-01-04T00:00:00Z",
                "execution_status": "completed",
                "spatial_holdout_untouched": True,
                "can_feed_decision_layer": False,
                "source_timestamp": "2024-01-04T00:00:00Z",
                "confidence_class": "low",
                "assumptions": "Synthetic runner fixture.",
            }
        )
    model_evidence = tmp_path / "model-evidence.csv"
    pd.DataFrame(rows, columns=MODEL_EVIDENCE_COLUMNS).to_csv(
        model_evidence,
        index=False,
        lineterminator="\n",
    )
    return {
        "manifest": manifest,
        "artifacts": artifacts,
        "authority": authority,
        "reviewer": reviewer_path,
        "holdout_receipt": holdout_receipt,
        "geometry": geometry,
        "grid_contract": grid_contract,
        "membership": membership,
        "reference_evidence": reference_evidence,
        "reference_receipt": reference_receipt,
        "model_evidence": model_evidence,
        "predictions": prediction_paths,
        "model_artifacts": model_artifacts,
        "model_contracts": model_contracts,
        "model_runs": model_runs,
    }


def _run_fixture(fixture: dict[str, object], output: Path) -> dict[str, Path]:
    return run_controlled_three_model_experiment(
        acquisition_manifest_path=fixture["manifest"],
        acquisition_artifact_paths=fixture["artifacts"],
        acquisition_authority_receipt_path=fixture["authority"],
        reviewer_calibration_receipt_path=fixture["reviewer"],
        holdout_receipt_path=fixture["holdout_receipt"],
        holdout_geometry_path=fixture["geometry"],
        holdout_grid_contract_path=fixture["grid_contract"],
        holdout_membership_path=fixture["membership"],
        reference_cell_receipt_path=fixture["reference_receipt"],
        reference_cell_evidence_path=fixture["reference_evidence"],
        model_evidence_manifest_path=fixture["model_evidence"],
        prediction_paths=fixture["predictions"],
        model_artifact_paths=fixture["model_artifacts"],
        model_contract_paths=fixture["model_contracts"],
        model_run_manifest_paths=fixture["model_runs"],
        signing_keys=SIGNING_KEYS,
        output_directory=output,
        generated_at_utc=datetime(2024, 1, 5, tzinfo=UTC),
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
