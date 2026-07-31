from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from floodguard.label_factory import query_models
from floodguard.label_factory.query_models import (
    QUERY_MODEL_WARNING,
    QueryModelDependencyError,
    QueryModelError,
    load_logistic_query_model,
    save_logistic_query_model,
    train_hist_gradient_boosting_query_model,
    train_logistic_query_model,
)

SAR_CHANGE_FEATURES = (
    "pre_vv_db",
    "event_vv_db",
    "pre_vh_db",
    "event_vh_db",
    "vv_change_db",
    "vh_change_db",
    "valid_data_fraction",
)


def test_logistic_query_model_is_auditable_and_query_only() -> None:
    frame = _training_frame()

    model = train_logistic_query_model(
        frame,
        feature_order=SAR_CHANGE_FEATURES,
        label_column="reviewed_target",
        model_id="mae-sai-q0-logistic",
        feature_schema_version="sar_change_v2",
        labelset_version="mae_sai_2024_labels_v0.1.0",
        trained_at_utc="2026-07-10T00:00:00Z",
    )
    probabilities = model.predict_probabilities(frame)
    predicted = (probabilities >= 0.5).astype(int)

    assert (predicted == frame["reviewed_target"]).mean() > 0.95
    assert model.feature_order == SAR_CHANGE_FEATURES
    assert len(model.feature_means) == len(SAR_CHANGE_FEATURES)
    assert len(model.feature_scales) == len(SAR_CHANGE_FEATURES)
    assert len(model.coefficients) == len(SAR_CHANGE_FEATURES)
    assert model.query_model_only is True
    assert model.eligible_for_decision_layer is False
    assert model.eligible_for_fpps is False
    assert model.eligible_for_warning is False
    artifact = model.to_artifact()
    assert artifact["feature_order"] == list(SAR_CHANGE_FEATURES)
    assert set(artifact["scaler"]["means"]) == set(SAR_CHANGE_FEATURES)
    assert set(artifact["coefficients"]["standardised_feature_coefficients"]) == set(
        SAR_CHANGE_FEATURES
    )
    assert artifact["warning"] == QUERY_MODEL_WARNING


def test_in_memory_model_cannot_relax_safety_flags() -> None:
    model = _train_logistic(_training_frame())

    with pytest.raises(QueryModelError, match="in-memory safety fields"):
        replace(model, eligible_for_fpps=True)


def test_logistic_persistence_reloads_identical_predictions_and_verifies_hash(
    tmp_path: Path,
) -> None:
    frame = _training_frame()
    model = _train_logistic(frame)
    before = model.predict_probabilities(frame)

    written = save_logistic_query_model(model, tmp_path / "query_model.json")
    loaded = load_logistic_query_model(written.model)
    reordered = frame.loc[:, ["reviewed_target", *reversed(SAR_CHANGE_FEATURES)]]
    after = loaded.predict_probabilities(reordered)

    assert written.model.exists()
    assert written.manifest.exists()
    np.testing.assert_array_equal(before.to_numpy(), after.to_numpy())
    manifest = json.loads(written.manifest.read_text(encoding="utf-8"))
    assert manifest["artifact_sha256"]
    assert manifest["query_model_only"] is True
    assert manifest["model_purpose"] == "query_ranking"
    assert manifest["eligible_for_review_queue"] is True
    assert manifest["eligible_for_training_after_human_review"] == "conditional"
    assert manifest["eligible_for_decision_layer"] is False
    assert manifest["eligible_for_fpps"] is False
    assert manifest["eligible_for_warning"] is False


def test_logistic_reload_rejects_checksum_tampering(tmp_path: Path) -> None:
    written = save_logistic_query_model(
        _train_logistic(_training_frame()),
        tmp_path / "query_model.json",
    )
    artifact = json.loads(written.model.read_text(encoding="utf-8"))
    artifact["coefficients"]["intercept"] = 999.0
    written.model.write_text(json.dumps(artifact), encoding="utf-8")

    with pytest.raises(QueryModelError, match="checksum"):
        load_logistic_query_model(written.model)


def test_logistic_reload_rejects_relaxed_safety_even_without_sidecar(
    tmp_path: Path,
) -> None:
    written = save_logistic_query_model(
        _train_logistic(_training_frame()),
        tmp_path / "query_model.json",
    )
    artifact = json.loads(written.model.read_text(encoding="utf-8"))
    artifact["safety"]["eligible_for_fpps"] = True
    written.model.write_text(json.dumps(artifact), encoding="utf-8")

    with pytest.raises(QueryModelError, match="eligible_for_fpps must remain False"):
        load_logistic_query_model(written.model, verify_manifest=False)


@pytest.mark.parametrize("invalid_label", [2, 3, 4, 255, -1, 0.5])
def test_training_rejects_non_binary_or_unknown_label_codes(
    invalid_label: float,
) -> None:
    frame = _training_frame()
    frame["reviewed_target"] = frame["reviewed_target"].astype(float)
    frame.loc[0, "reviewed_target"] = invalid_label

    with pytest.raises(QueryModelError, match="explicit reviewed 0/1"):
        _train_logistic(frame)


def test_training_rejects_missing_and_single_class_evidence() -> None:
    with pytest.raises(QueryModelError, match="missing required columns"):
        _train_logistic(_training_frame().drop(columns=["vh_change_db"]))

    one_class = _training_frame()
    one_class["reviewed_target"] = 1
    with pytest.raises(QueryModelError, match="both explicit classes"):
        _train_logistic(one_class)


def test_hist_gradient_boosting_has_clear_optional_dependency_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_module(_name: str) -> object:
        raise ModuleNotFoundError("No module named 'sklearn'")

    monkeypatch.setattr(query_models.importlib, "import_module", missing_module)

    with pytest.raises(QueryModelDependencyError, match=r"pip install -e .\[ml\]"):
        train_hist_gradient_boosting_query_model(
            _training_frame(),
            feature_order=SAR_CHANGE_FEATURES,
            label_column="reviewed_target",
            model_id="mae-sai-q0-hgb",
            feature_schema_version="sar_change_v2",
            labelset_version="mae_sai_2024_labels_v0.1.0",
        )


def test_hist_gradient_boosting_forces_no_internal_random_validation_split(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeHistGradientBoostingClassifier:
        def __init__(self, **parameters: object) -> None:
            self.parameters = parameters

        def fit(
            self,
            features: np.ndarray,
            labels: np.ndarray,
            *,
            sample_weight: np.ndarray,
        ) -> "FakeHistGradientBoostingClassifier":
            assert len(features) == len(labels) == len(sample_weight)
            return self

        def predict_proba(self, features: np.ndarray) -> np.ndarray:
            positive = 1.0 / (1.0 + np.exp(-features[:, 4]))
            return np.column_stack([1.0 - positive, positive])

        def get_params(self, deep: bool = False) -> dict[str, object]:
            assert deep is False
            return dict(self.parameters)

    monkeypatch.setattr(
        query_models.importlib,
        "import_module",
        lambda _name: SimpleNamespace(
            HistGradientBoostingClassifier=FakeHistGradientBoostingClassifier
        ),
    )
    model = train_hist_gradient_boosting_query_model(
        _training_frame(),
        feature_order=SAR_CHANGE_FEATURES,
        label_column="reviewed_target",
        model_id="mae-sai-q0-hgb",
        feature_schema_version="sar_change_v2",
        labelset_version="mae_sai_2024_labels_v0.1.0",
        trained_at_utc="2026-07-10T00:00:00Z",
    )
    manifest = model.to_manifest()

    assert manifest["estimator_parameters"]["early_stopping"] is False
    assert manifest["query_model_only"] is True
    assert manifest["model_purpose"] == "query_ranking"
    assert manifest["eligible_for_review_queue"] is True
    assert manifest["eligible_for_training_after_human_review"] == "conditional"
    assert manifest["eligible_for_decision_layer"] is False
    assert manifest["eligible_for_fpps"] is False
    assert manifest["eligible_for_warning"] is False
    assert model.predict_probabilities(_training_frame()).between(0.0, 1.0).all()

    with pytest.raises(QueryModelError, match="early_stopping must be False"):
        train_hist_gradient_boosting_query_model(
            _training_frame(),
            feature_order=SAR_CHANGE_FEATURES,
            label_column="reviewed_target",
            model_id="unsafe-hgb",
            feature_schema_version="sar_change_v2",
            labelset_version="mae_sai_2024_labels_v0.1.0",
            estimator_parameters={"early_stopping": True},
        )


def _train_logistic(frame: pd.DataFrame):
    return train_logistic_query_model(
        frame,
        feature_order=SAR_CHANGE_FEATURES,
        label_column="reviewed_target",
        model_id="mae-sai-q0-logistic",
        feature_schema_version="sar_change_v2",
        labelset_version="mae_sai_2024_labels_v0.1.0",
        epochs=800,
        trained_at_utc="2026-07-10T00:00:00Z",
    )


def _training_frame() -> pd.DataFrame:
    rows = []
    for index in range(-30, 31):
        vv_change_db = index / 10.0
        vh_change_db = vv_change_db + (0.15 if index % 2 else -0.15)
        pre_vv_db = -11.0 + index / 100.0
        pre_vh_db = -17.0 + index / 100.0
        rows.append(
            {
                "pre_vv_db": pre_vv_db,
                "event_vv_db": pre_vv_db - vv_change_db,
                "pre_vh_db": pre_vh_db,
                "event_vh_db": pre_vh_db - vh_change_db,
                "vv_change_db": vv_change_db,
                "vh_change_db": vh_change_db,
                "valid_data_fraction": 1.0,
                "reviewed_target": int(vv_change_db + vh_change_db > 0.0),
            }
        )
    return pd.DataFrame(rows)
