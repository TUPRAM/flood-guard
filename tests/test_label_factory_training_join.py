from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from floodguard.label_factory.committee import (
    CommitteeError,
    train_and_write_query_committee,
)
from floodguard.label_factory.feature_schema import get_feature_schema
from floodguard.label_factory.training_join import (
    DERIVATION_MANIFEST_FILENAME,
    TRAINING_TABLE_FILENAME,
    TrainingJoinError,
    build_and_write_training_table,
    verify_training_derivation,
)
from floodguard.label_factory.versioning import (
    build_labelset_manifest,
    freeze_labelset_manifest,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
FEATURES = get_feature_schema("sar_change_v2").required_feature_names
GRID_HASH = "e" * 64


class _FakeHistGradientBoostingClassifier:
    def __init__(self, **parameters: object) -> None:
        self.parameters = dict(parameters)
        self.center = 0.0

    def fit(
        self,
        features: np.ndarray,
        labels: np.ndarray,
        sample_weight: np.ndarray | None = None,
    ) -> _FakeHistGradientBoostingClassifier:
        del labels, sample_weight
        self.center = float(np.asarray(features, dtype=float)[:, 0].mean())
        return self

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        values = np.asarray(features, dtype=float)[:, 0]
        positive = 1.0 / (1.0 + np.exp(-np.clip(values - self.center, -20, 20)))
        return np.column_stack([1.0 - positive, positive])

    def get_params(self, deep: bool = False) -> dict[str, object]:
        del deep
        return dict(self.parameters)


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _release_fixture(tmp_path: Path) -> dict[str, Path]:
    cells_path = tmp_path / "final_cells.csv"
    labels = [0, 1, 2, 3, 4, 255, 1, 0]
    rows: list[dict[str, object]] = []
    for index, label in enumerate(labels):
        query_id = "QUERY-A" if index < 4 else "QUERY-B"
        adjudicated = index in {1, 5}
        rows.append(
            {
                "event_id": "TH-MAESAI-2024-09",
                "tile_id": "TILE-A" if query_id == "QUERY-A" else "TILE-B",
                "query_region_id": query_id,
                "cell_id": f"{query_id}_R{index:04d}_C0000",
                "row_index": index,
                "column_index": 0,
                "label_code": label,
                "source_annotation_id": "" if adjudicated else "ANN-A",
                "source_adjudication_id": "ADJ-1" if adjudicated else "",
                "grid_contract_sha256": GRID_HASH,
                "source_registry_sha256": "f" * 64,
            }
        )
    pd.DataFrame(rows).to_csv(cells_path, index=False, lineterminator="\n")
    cell_hash = hashlib.sha256(cells_path.read_bytes()).hexdigest()
    manifest = build_labelset_manifest(
        labelset_name="mae_sai_labels",
        version="0.1.0",
        change_kind="initial",
        label_content={
            "QUERY-A": labels[:4],
            "QUERY-B": labels[4:],
        },
        metadata={"qa_ready": True},
        semantics={"taxonomy": "flood_label_v1"},
        source_annotation_ids=["ANN-A"],
        raster_sha256_by_name={"final_cells": cell_hash},
        created_at_utc=datetime(2026, 7, 10, tzinfo=timezone.utc),
    )
    manifest_path = tmp_path / "labelset.json"
    freeze_labelset_manifest(manifest, manifest_path)

    receipt_unsigned = {
        "artifact_schema": "floodguard.labelset_validation_receipt.v1",
        "labelset_id": manifest.labelset_id,
        "labelset_manifest_sha256": manifest.manifest_sha256,
        "validated_at_utc": "2026-07-10T01:00:00Z",
        "qa_report_sha256": "1" * 64,
        "qa_evidence_manifest_sha256": "2" * 64,
        "reviewer_calibration_receipt_sha256": "5" * 64,
        "agreement_evidence_sha256": "3" * 64,
        "raster_lineage_sha256": "4" * 64,
        "raster_sha256_by_name": {"final_cells": cell_hash},
        "grid_contract_sha256": GRID_HASH,
        "query_region_ids": ["QUERY-A", "QUERY-B"],
        "qa_ready": True,
        "open_adjudication_count": 0,
        "eligible_for_query_model_training": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }
    receipt = {
        **receipt_unsigned,
        "receipt_sha256": _canonical_sha256(receipt_unsigned),
    }
    receipt_path = tmp_path / "validation_receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )

    feature_rows: list[dict[str, object]] = []
    for index, cell in enumerate(rows):
        feature: dict[str, object] = {
            "sample_id": cell["cell_id"],
            "query_region_id": cell["query_region_id"],
            "cell_id": cell["cell_id"],
            "grid_contract_sha256": GRID_HASH,
            "spatial_group_id": (
                "BLOCK-A" if cell["query_region_id"] == "QUERY-A" else "BLOCK-B"
            ),
            "dataset_role": "training_and_query_pool",
            "feature_schema_version": "sar_change_v2",
        }
        for feature_index, name in enumerate(FEATURES):
            feature[name] = float(index + feature_index * 0.1)
        feature_rows.append(feature)
    features_path = tmp_path / "features.csv"
    pd.DataFrame(feature_rows).to_csv(
        features_path, index=False, lineterminator="\n"
    )
    return {
        "cells": cells_path,
        "features": features_path,
        "labelset": manifest_path,
        "receipt": receipt_path,
    }


def _build(tmp_path: Path) -> tuple[dict[str, Path], Path]:
    fixture = _release_fixture(tmp_path)
    output = tmp_path / "training-join"
    build_and_write_training_table(
        labelset_manifest_path=fixture["labelset"],
        release_validation_receipt_path=fixture["receipt"],
        final_cell_csv=fixture["cells"],
        feature_csv=fixture["features"],
        output_directory=output,
        created_at_utc="2026-07-10T02:00:00Z",
    )
    return fixture, output


def test_builder_derives_targets_sources_and_self_hashed_manifest(
    tmp_path: Path,
) -> None:
    fixture, output = _build(tmp_path)
    training_path = output / TRAINING_TABLE_FILENAME
    manifest_path = output / DERIVATION_MANIFEST_FILENAME
    training = pd.read_csv(training_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert set(training["label_code"]) == {0, 1, 2}
    assert training.loc[training["label_code"] == 1, "binary_target"].eq(1).all()
    assert training.loc[training["label_code"].isin([0, 2]), "binary_target"].eq(0).all()
    assert set(training["label_source_type"]) == {
        "human_reviewed",
        "human_adjudicated",
    }
    assert training["sample_id"].equals(training["cell_id"])
    assert training["dataset_role"].eq("training_and_query_pool").all()
    assert training["event_id"].eq("TH-MAESAI-2024-09").all()
    assert set(training["tile_id"]) == {"TILE-A", "TILE-B"}
    assert training["source_registry_sha256"].eq("f" * 64).all()
    assert training["query_model_only"].eq(True).all()  # noqa: E712
    assert training["eligible_for_decision_layer"].eq(False).all()  # noqa: E712
    assert manifest["excluded_label_codes"] == {"3": 1, "4": 1, "255": 1}
    unsigned = dict(manifest)
    declared_hash = unsigned.pop("manifest_sha256")
    assert declared_hash == _canonical_sha256(unsigned)

    verified = verify_training_derivation(
        training_path,
        manifest_path,
        fixture["receipt"],
        fixture["labelset"],
    )
    assert verified.row_count == 5
    assert verified.grid_contract_sha256 == GRID_HASH
    assert verified.query_region_ids == ("QUERY-A", "QUERY-B")

    with pytest.raises(TrainingJoinError, match="cannot be overwritten"):
        build_and_write_training_table(
            labelset_manifest_path=fixture["labelset"],
            release_validation_receipt_path=fixture["receipt"],
            final_cell_csv=fixture["cells"],
            feature_csv=fixture["features"],
            output_directory=output,
        )


@pytest.mark.parametrize(
    ("forged_column", "forged_value"),
    [
        ("binary_target", 1),
        ("label_source_type", "human_reviewed"),
        ("eligible_for_query_model_training", True),
    ],
)
def test_builder_rejects_caller_forged_label_and_eligibility_fields(
    tmp_path: Path,
    forged_column: str,
    forged_value: object,
) -> None:
    fixture = _release_fixture(tmp_path)
    features = pd.read_csv(fixture["features"])
    features[forged_column] = forged_value
    features.to_csv(fixture["features"], index=False, lineterminator="\n")

    with pytest.raises(TrainingJoinError, match="caller-supplied"):
        build_and_write_training_table(
            labelset_manifest_path=fixture["labelset"],
            release_validation_receipt_path=fixture["receipt"],
            final_cell_csv=fixture["cells"],
            feature_csv=fixture["features"],
            output_directory=tmp_path / "blocked",
        )


def test_verifier_rejects_mutated_training_csv(tmp_path: Path) -> None:
    fixture, output = _build(tmp_path)
    training_path = output / TRAINING_TABLE_FILENAME
    training = pd.read_csv(training_path)
    training.loc[0, "binary_target"] = 1 - int(training.loc[0, "binary_target"])
    training.to_csv(training_path, index=False, lineterminator="\n")

    with pytest.raises(TrainingJoinError, match="SHA-256"):
        verify_training_derivation(
            training_path,
            output / DERIVATION_MANIFEST_FILENAME,
            fixture["receipt"],
            fixture["labelset"],
        )


def test_verifier_rejects_different_self_consistent_receipt(tmp_path: Path) -> None:
    fixture, output = _build(tmp_path)
    wrong = json.loads(fixture["receipt"].read_text(encoding="utf-8"))
    wrong["validated_at_utc"] = "2026-07-10T03:00:00Z"
    wrong.pop("receipt_sha256")
    wrong["receipt_sha256"] = _canonical_sha256(wrong)
    wrong_path = tmp_path / "wrong_receipt.json"
    wrong_path.write_text(json.dumps(wrong, sort_keys=True, indent=2) + "\n")

    with pytest.raises(TrainingJoinError, match="receipt"):
        verify_training_derivation(
            output / TRAINING_TABLE_FILENAME,
            output / DERIVATION_MANIFEST_FILENAME,
            wrong_path,
            fixture["labelset"],
        )


def test_builder_rejects_grid_mismatch_and_reserved_roles(tmp_path: Path) -> None:
    fixture = _release_fixture(tmp_path)
    features = pd.read_csv(fixture["features"])
    features.loc[0, "grid_contract_sha256"] = "f" * 64
    features.to_csv(fixture["features"], index=False, lineterminator="\n")
    with pytest.raises(TrainingJoinError, match="missing exact"):
        build_and_write_training_table(
            labelset_manifest_path=fixture["labelset"],
            release_validation_receipt_path=fixture["receipt"],
            final_cell_csv=fixture["cells"],
            feature_csv=fixture["features"],
            output_directory=tmp_path / "grid-blocked",
        )

    features.loc[0, "grid_contract_sha256"] = GRID_HASH
    features.loc[0, "dataset_role"] = "untouched_geographic_test"
    features.to_csv(fixture["features"], index=False, lineterminator="\n")
    with pytest.raises(TrainingJoinError, match="calibration/development/test"):
        build_and_write_training_table(
            labelset_manifest_path=fixture["labelset"],
            release_validation_receipt_path=fixture["receipt"],
            final_cell_csv=fixture["cells"],
            feature_csv=fixture["features"],
            output_directory=tmp_path / "role-blocked",
        )


def test_training_join_cli_help_exposes_authoritative_inputs() -> None:
    run = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "build_label_factory_training_table.py"),
            "--help",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert run.returncode == 0
    assert "--release-validation-receipt" in run.stdout
    assert "--final-cell-csv" in run.stdout
    assert "--feature-csv" in run.stdout


def test_committee_file_entrypoint_rechecks_derivation_and_records_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture, join_output = _build(tmp_path)
    monkeypatch.setattr(
        "floodguard.label_factory.query_models._load_sklearn_ensemble",
        lambda: SimpleNamespace(
            HistGradientBoostingClassifier=_FakeHistGradientBoostingClassifier
        ),
    )
    pool_rows: list[dict[str, object]] = []
    for index in range(3):
        row: dict[str, object] = {
            "sample_id": f"POOL-CELL-{index}",
            "query_region_id": f"POOL-QUERY-{index}",
            "dataset_role": "training_and_query_pool",
            "feature_schema_version": "sar_change_v2",
            "eligible_for_review_queue": True,
            "query_model_only": True,
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
        }
        for feature_index, name in enumerate(FEATURES):
            row[name] = float(index + feature_index * 0.1)
        pool_rows.append(row)
    pool_path = tmp_path / "pool.csv"
    pd.DataFrame(pool_rows).to_csv(pool_path, index=False, lineterminator="\n")
    written = train_and_write_query_committee(
        join_output / TRAINING_TABLE_FILENAME,
        pool_path,
        tmp_path / "committee",
        training_derivation_manifest=join_output / DERIVATION_MANIFEST_FILENAME,
        release_validation_receipt=fixture["receipt"],
        labelset_manifest=fixture["labelset"],
        n_splits=2,
        n_repeats=1,
        logistic_epochs=10,
        run_id="provenance-test",
        trained_at_utc="2026-07-10T03:00:00Z",
    )
    run = json.loads(written.run_manifest.read_text(encoding="utf-8"))
    verified = run["inputs"]["verified_training_derivation"]
    assert verified["training_csv_sha256"] == hashlib.sha256(
        (join_output / TRAINING_TABLE_FILENAME).read_bytes()
    ).hexdigest()
    assert verified["release_validation_receipt_sha256"] == json.loads(
        fixture["receipt"].read_text(encoding="utf-8")
    )["receipt_sha256"]
    assert set(run["inputs"]["provenance_sources"]) == {
        "training_derivation_manifest",
        "release_validation_receipt",
        "labelset_manifest",
    }

    training = pd.read_csv(join_output / TRAINING_TABLE_FILENAME)
    training.loc[0, "binary_target"] = 1 - int(training.loc[0, "binary_target"])
    training.to_csv(
        join_output / TRAINING_TABLE_FILENAME,
        index=False,
        lineterminator="\n",
    )
    with pytest.raises(CommitteeError, match="derivation provenance"):
        train_and_write_query_committee(
            join_output / TRAINING_TABLE_FILENAME,
            pool_path,
            tmp_path / "blocked-committee",
            training_derivation_manifest=join_output / DERIVATION_MANIFEST_FILENAME,
            release_validation_receipt=fixture["receipt"],
            labelset_manifest=fixture["labelset"],
            n_splits=2,
            n_repeats=1,
        )
