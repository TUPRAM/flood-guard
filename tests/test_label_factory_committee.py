from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from floodguard.label_factory.committee import (
    CommitteeDependencyError,
    CommitteeError,
    make_repeated_spatial_group_folds,
    train_query_committee,
    write_query_committee_outputs,
)
from floodguard.label_factory.feature_schema import get_feature_schema
from floodguard.label_factory.query_models import QueryModelDependencyError


REPO_ROOT = Path(__file__).resolve().parents[1]
FEATURES = get_feature_schema("sar_change_v2").required_feature_names
LABELSET_SHA256 = "c" * 64


class _FakeHistGradientBoostingClassifier:
    """Small deterministic sklearn-shaped estimator for orchestration tests."""

    def __init__(self, **parameters: object) -> None:
        self.parameters = dict(parameters)
        self.center = 0.0
        self.scale = 1.0

    def fit(
        self,
        features: np.ndarray,
        labels: np.ndarray,
        sample_weight: np.ndarray | None = None,
    ) -> _FakeHistGradientBoostingClassifier:
        del labels, sample_weight
        values = np.asarray(features, dtype=float)[:, 0]
        self.center = float(values.mean())
        scale = float(values.std())
        self.scale = scale if scale > 0.0 else 1.0
        return self

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        values = np.asarray(features, dtype=float)[:, 0]
        logits = np.clip((values - self.center) / self.scale, -20.0, 20.0)
        positive = 1.0 / (1.0 + np.exp(-logits))
        return np.column_stack([1.0 - positive, positive])

    def get_params(self, deep: bool = False) -> dict[str, object]:
        del deep
        return dict(self.parameters)


def _install_fake_boosted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "floodguard.label_factory.query_models._load_sklearn_ensemble",
        lambda: SimpleNamespace(
            HistGradientBoostingClassifier=_FakeHistGradientBoostingClassifier
        ),
    )


def _training_frame(*, groups: int = 6, rows_per_group: int = 4) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for group in range(groups):
        for offset in range(rows_per_group):
            target = offset % 2
            row: dict[str, object] = {
                "sample_id": f"train-{group:02d}-{offset:02d}",
                "query_region_id": f"query-{group:02d}",
                "spatial_group_id": f"block-{group:02d}",
                "dataset_role": "training_and_query_pool",
                "label_source_type": (
                    "human_reviewed" if offset < 3 else "human_adjudicated"
                ),
                "eligible_for_query_model_training": True,
                "labelset_version": "labelset-v1",
                "labelset_manifest_sha256": LABELSET_SHA256,
                "binary_target": target,
            }
            for feature_index, feature in enumerate(FEATURES):
                row[feature] = float(
                    group * 0.5 + offset + feature_index * 0.01 + target * 0.2
                )
            rows.append(row)
    return pd.DataFrame(rows)


def _pool_frame(*, rows: int = 7) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for index in range(rows):
        row: dict[str, object] = {
            "sample_id": f"pool-{index:03d}",
            "query_region_id": f"pool-query-{index // 2:03d}",
            "dataset_role": "training_and_query_pool",
            "eligible_for_review_queue": True,
            "query_model_only": True,
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
            "feature_schema_version": "sar_change_v2",
            "labelset_version": "labelset-v1",
            "labelset_manifest_sha256": LABELSET_SHA256,
        }
        for feature_index, feature in enumerate(FEATURES):
            row[feature] = float(index * 0.25 + feature_index * 0.01)
        records.append(row)
    return pd.DataFrame(records)


def _train_with_fake(monkeypatch: pytest.MonkeyPatch):
    _install_fake_boosted(monkeypatch)
    return train_query_committee(
        _training_frame(),
        _pool_frame(),
        labelset_version="labelset-v1",
        labelset_manifest_sha256=LABELSET_SHA256,
        n_splits=3,
        n_repeats=2,
        random_seed=17,
        run_id="committee-test-run",
        trained_at_utc="2026-07-10T01:02:03Z",
        logistic_epochs=30,
    )


def test_repeated_spatial_folds_are_deterministic_and_never_split_groups() -> None:
    frame = _training_frame(groups=7)
    first = make_repeated_spatial_group_folds(
        frame, n_splits=3, n_repeats=3, random_seed=42
    )
    second = make_repeated_spatial_group_folds(
        frame, n_splits=3, n_repeats=3, random_seed=42
    )

    assert first == second
    signatures = {
        tuple(fold.validation_groups for fold in first if fold.repeat_index == repeat)
        for repeat in range(1, 4)
    }
    assert len(signatures) > 1
    for repeat in range(1, 4):
        repeat_folds = [fold for fold in first if fold.repeat_index == repeat]
        assigned = [group for fold in repeat_folds for group in fold.validation_groups]
        assert sorted(assigned) == [f"block-{index:02d}" for index in range(7)]
        assert len(assigned) == len(set(assigned))
        assert all(fold.training_rows + fold.validation_rows == len(frame) for fold in repeat_folds)


def test_spatial_fold_generation_fails_closed_on_one_class_training() -> None:
    frame = pd.DataFrame(
        {
            "spatial_group_id": ["positive", "positive", "negative", "negative"],
            "binary_target": [1, 1, 0, 0],
        }
    )

    with pytest.raises(CommitteeError, match="one-class training complement"):
        make_repeated_spatial_group_folds(frame, n_splits=2, n_repeats=1)


@pytest.mark.parametrize(
    "forbidden_role",
    [
        "reviewer_calibration",
        "fixed_within_event_development",
        "untouched_geographic_test",
    ],
)
def test_training_rejects_every_non_pool_dataset_role(forbidden_role: str) -> None:
    training = _training_frame()
    training.loc[0, "dataset_role"] = forbidden_role

    with pytest.raises(CommitteeError, match="accepts only dataset_role"):
        train_query_committee(
            training,
            _pool_frame(),
            labelset_version="labelset-v1",
            labelset_manifest_sha256=LABELSET_SHA256,
            n_splits=3,
            n_repeats=1,
        )


@pytest.mark.parametrize(
    ("column", "bad_value", "message"),
    [
        (
            "eligible_for_query_model_training",
            1,
            "literal boolean true",
        ),
        ("label_source_type", "weak_reference", "human_reviewed"),
        ("labelset_version", "labelset-v0", "must match labelset_version"),
        (
            "labelset_manifest_sha256",
            "d" * 64,
            "must match the frozen labelset_manifest_sha256",
        ),
        ("binary_target", 255, "not explicit 0/1"),
        ("sample_id", "", "stable non-blank identifier"),
    ],
)
def test_training_contract_rejects_unsafe_rows(
    column: str,
    bad_value: object,
    message: str,
) -> None:
    training = _training_frame()
    if column == "eligible_for_query_model_training":
        training[column] = training[column].astype(object)
    training.loc[0, column] = bad_value

    with pytest.raises(CommitteeError, match=message):
        train_query_committee(
            training,
            _pool_frame(),
            labelset_version="labelset-v1",
            labelset_manifest_sha256=LABELSET_SHA256,
            n_splits=3,
            n_repeats=1,
        )


def test_query_committee_rejects_query_overlap_even_when_sample_ids_differ() -> None:
    training = _training_frame()
    pool = _pool_frame()
    pool.loc[0, "query_region_id"] = str(training.loc[0, "query_region_id"])

    with pytest.raises(CommitteeError, match="overlapping query_region_id"):
        train_query_committee(
            training,
            pool,
            labelset_version="labelset-v1",
            labelset_manifest_sha256=LABELSET_SHA256,
            n_splits=3,
            n_repeats=1,
        )


def test_query_committee_generates_complete_oof_and_pool_scores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _train_with_fake(monkeypatch)

    assert len(result.folds) == 6
    assert len(result.oof_scores) == len(_training_frame()) * 2
    assert len(result.pool_scores) == len(_pool_frame())
    assert (
        result.oof_scores.groupby(["repeat_index", "sample_id"]).size() == 1
    ).all()
    for column in ("logistic_query_score", "boosted_query_score"):
        assert result.oof_scores[column].between(0.0, 1.0).all()
        assert result.pool_scores[column].between(0.0, 1.0).all()
    assert result.oof_scores["query_model_only"].eq(True).all()  # noqa: E712
    assert result.oof_scores["eligible_for_decision_layer"].eq(False).all()  # noqa: E712
    assert result.oof_scores["eligible_for_fpps"].eq(False).all()  # noqa: E712
    assert result.oof_scores["eligible_for_warning"].eq(False).all()  # noqa: E712
    assert not any("threshold" in column.lower() for column in result.oof_scores)
    assert not any("threshold" in column.lower() for column in result.pool_scores)
    assert result.boosted_model.to_manifest()["estimator_parameters"][
        "early_stopping"
    ] is False


def test_writer_persists_hashed_non_executable_audit_artifacts_without_overwrite(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result = _train_with_fake(monkeypatch)
    output = tmp_path / "committee-run"

    written = write_query_committee_outputs(result, output)

    assert all(path.is_file() for path in written.as_dict().values())
    logistic_bytes = written.logistic_model.read_bytes()
    logistic_sidecar = json.loads(written.logistic_manifest.read_text(encoding="utf-8"))
    assert logistic_sidecar["artifact_sha256"] == hashlib.sha256(
        logistic_bytes
    ).hexdigest()
    boosted = json.loads(written.boosted_manifest.read_text(encoding="utf-8"))
    assert boosted["persistence"] == "non_executable_manifest_only"
    assert boosted["serialized_estimator"] is False
    assert boosted["estimator_parameters"]["early_stopping"] is False
    run = json.loads(written.run_manifest.read_text(encoding="utf-8"))
    assert run["safety"]["query_model_only"] is True
    assert run["safety"]["eligible_for_decision_layer"] is False
    assert run["safety"]["eligible_for_fpps"] is False
    assert run["safety"]["eligible_for_warning"] is False
    assert run["safety"]["classification_cutoff_selected"] is False
    assert run["label_contract"]["labelset_manifest_sha256"] == LABELSET_SHA256
    assert "threshold" not in written.run_manifest.read_text(encoding="utf-8").lower()
    for artifact in run["artifacts"]:
        path = output / artifact["file"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]

    with pytest.raises(CommitteeError, match="will not be overwritten"):
        write_query_committee_outputs(result, output)


def test_missing_sklearn_raises_clear_optional_dependency_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing() -> object:
        raise QueryModelDependencyError("missing")

    monkeypatch.setattr(
        "floodguard.label_factory.query_models._load_sklearn_ensemble", missing
    )

    with pytest.raises(CommitteeDependencyError, match="optional scikit-learn"):
        train_query_committee(
            _training_frame(),
            _pool_frame(),
            labelset_version="labelset-v1",
            labelset_manifest_sha256=LABELSET_SHA256,
            n_splits=3,
            n_repeats=1,
            logistic_epochs=5,
        )


@pytest.mark.parametrize(
    "legacy_schema",
    ["legacy_synthetic_sar_v1", "legacy_real_weak_sar_v1"],
)
def test_query_committee_rejects_legacy_feature_schemas(legacy_schema: str) -> None:
    with pytest.raises(CommitteeError, match="only the canonical non-legacy"):
        train_query_committee(
            _training_frame(),
            _pool_frame(),
            labelset_version="labelset-v1",
            labelset_manifest_sha256=LABELSET_SHA256,
            feature_schema_version=legacy_schema,
            n_splits=3,
            n_repeats=1,
        )


@pytest.mark.skipif(
    importlib.util.find_spec("sklearn") is None,
    reason="real optional scikit-learn path is not installed",
)
def test_real_hist_gradient_boosting_path_runs_end_to_end(tmp_path: Path) -> None:
    result = train_query_committee(
        _training_frame(groups=4, rows_per_group=6),
        _pool_frame(rows=4),
        labelset_version="labelset-v1",
        labelset_manifest_sha256=LABELSET_SHA256,
        n_splits=2,
        n_repeats=1,
        random_seed=5,
        run_id="real-sklearn-test",
        trained_at_utc="2026-07-10T02:03:04Z",
        logistic_epochs=20,
        boosted_parameters={"max_iter": 5, "min_samples_leaf": 2},
    )

    manifest = result.boosted_model.to_manifest()
    assert manifest["model_family"] == "hist_gradient_boosting_classifier"
    assert manifest["estimator_parameters"]["early_stopping"] is False
    assert len(result.oof_scores) == 24
    assert result.pool_scores["boosted_query_score"].between(0.0, 1.0).all()
    written = write_query_committee_outputs(result, tmp_path / "real-ml-run")
    persisted = json.loads(written.boosted_manifest.read_text(encoding="utf-8"))
    assert persisted["persistence"] == "non_executable_manifest_only"
    assert written.run_manifest.is_file()


def test_cli_help_and_blocked_exit_contract(tmp_path: Path) -> None:
    script = REPO_ROOT / "scripts" / "train_query_committee.py"
    help_run = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert help_run.returncode == 0
    assert "--training-csv" in help_run.stdout
    assert "--group-column" in help_run.stdout
    assert "--labelset-manifest" in help_run.stdout
    assert "--training-derivation-manifest" in help_run.stdout
    assert "--release-validation-receipt" in help_run.stdout

    blocked = subprocess.run(
        [
            sys.executable,
            str(script),
            "--training-csv",
            str(tmp_path / "missing-training.csv"),
            "--pool-csv",
            str(tmp_path / "missing-pool.csv"),
            "--output-directory",
            str(tmp_path / "new-run"),
            "--labelset-manifest",
            str(tmp_path / "missing-labelset.json"),
            "--training-derivation-manifest",
            str(tmp_path / "missing-derivation.json"),
            "--release-validation-receipt",
            str(tmp_path / "missing-receipt.json"),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert blocked.returncode == 2
    assert "BLOCKED:" in blocked.stderr
