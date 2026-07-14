"""Query-only models for prioritising human flood-label review.

The persisted logistic model is intentionally small and auditable.  The
gradient-boosted challenger is an optional, lazily imported scikit-learn model.
Both wrappers hard-code their safety status: they may rank annotation queries,
but they may not feed the decision layer, FPPS, action classes, or warnings.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import importlib
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from floodguard.label_factory.contracts import QUERY_MODEL_ELIGIBILITY
from floodguard.label_factory.feature_schema import FeatureSchemaError, get_feature_schema


LOGISTIC_ARTIFACT_SCHEMA = "floodguard.logistic_query_model.v1"
QUERY_MODEL_WARNING = (
    "Query-model only. Selects regions for human review; does not create flood "
    "truth and is ineligible for the FloodGuard decision layer, FPPS, action "
    "classes, or warnings."
)


class QueryModelError(ValueError):
    """Raised when query-model data, metadata, or artifacts are invalid."""


class QueryModelDependencyError(RuntimeError):
    """Raised when an explicitly requested optional ML dependency is absent."""


@dataclass(frozen=True)
class QueryModelArtifacts:
    """Paths written for one persisted logistic query model."""

    model: Path
    manifest: Path


@dataclass(frozen=True)
class LogisticQueryModel:
    """Persistable, standardised logistic query baseline.

    Coefficients are defined over standardised features in ``feature_order``.
    No learned classification threshold is stored because this model's only
    valid output is a continuous score for active-learning acquisition.
    """

    model_id: str
    feature_order: tuple[str, ...]
    feature_means: tuple[float, ...]
    feature_scales: tuple[float, ...]
    coefficients: tuple[float, ...]
    intercept: float
    feature_schema_version: str
    labelset_version: str
    trained_at_utc: str
    training_rows: int
    positive_rows: int
    negative_rows: int
    epochs: int
    learning_rate: float
    l2: float
    balanced_class_weights: bool

    model_family: str = "logistic_regression_from_scratch"
    query_model_only: bool = True
    eligible_for_decision_layer: bool = False
    eligible_for_fpps: bool = False
    eligible_for_warning: bool = False

    def __post_init__(self) -> None:
        """Reject any in-memory attempt to relax the query-only boundary."""

        _require_hard_query_model_flags(
            self.query_model_only,
            self.eligible_for_decision_layer,
            self.eligible_for_fpps,
            self.eligible_for_warning,
        )

    def predict_probabilities(self, frame: pd.DataFrame) -> pd.Series:
        """Return query scores in ``[0, 1]`` using the persisted feature order."""

        import numpy as np

        values = _validated_prediction_matrix(frame, self.feature_order)
        mean = np.asarray(self.feature_means, dtype=float)
        scale = np.asarray(self.feature_scales, dtype=float)
        coefficients = np.asarray(self.coefficients, dtype=float)
        standardised = (values - mean) / scale
        logits = np.clip(standardised @ coefficients + self.intercept, -40.0, 40.0)
        probabilities = 1.0 / (1.0 + np.exp(-logits))
        return pd.Series(
            probabilities,
            index=frame.index,
            name="query_probability_0_1",
            dtype="float64",
        )

    def to_artifact(self) -> dict[str, object]:
        """Return the complete reloadable, audit-friendly JSON artifact."""

        return {
            "artifact_schema": LOGISTIC_ARTIFACT_SCHEMA,
            "model_id": self.model_id,
            "model_family": self.model_family,
            "feature_order": list(self.feature_order),
            "feature_schema_version": self.feature_schema_version,
            "labelset_version": self.labelset_version,
            "trained_at_utc": self.trained_at_utc,
            "scaler": {
                "kind": "standard",
                "means": dict(zip(self.feature_order, self.feature_means)),
                "scales": dict(zip(self.feature_order, self.feature_scales)),
                "zero_variance_scale_replacement": 1.0,
            },
            "coefficients": {
                "standardised_feature_coefficients": dict(
                    zip(self.feature_order, self.coefficients)
                ),
                "intercept": self.intercept,
            },
            "training": {
                "rows": self.training_rows,
                "positive_rows": self.positive_rows,
                "negative_rows": self.negative_rows,
                "epochs": self.epochs,
                "learning_rate": self.learning_rate,
                "l2": self.l2,
                "balanced_class_weights": self.balanced_class_weights,
            },
            "safety": _safety_manifest(),
            "warning": QUERY_MODEL_WARNING,
        }

    def to_manifest(self) -> dict[str, object]:
        """Return compact lineage, feature, training, and safety metadata."""

        return {
            "model_id": self.model_id,
            "model_family": self.model_family,
            "feature_order": list(self.feature_order),
            "feature_schema_version": self.feature_schema_version,
            "labelset_version": self.labelset_version,
            "trained_at_utc": self.trained_at_utc,
            "training_rows": self.training_rows,
            "positive_rows": self.positive_rows,
            "negative_rows": self.negative_rows,
            **_safety_manifest(),
            "warning": QUERY_MODEL_WARNING,
        }


@dataclass(frozen=True)
class HistGradientBoostingQueryModel:
    """In-memory optional nonlinear challenger used only for query ranking."""

    estimator: object
    model_id: str
    feature_order: tuple[str, ...]
    feature_schema_version: str
    labelset_version: str
    trained_at_utc: str
    training_rows: int
    positive_rows: int
    negative_rows: int

    model_family: str = "hist_gradient_boosting_classifier"
    query_model_only: bool = True
    eligible_for_decision_layer: bool = False
    eligible_for_fpps: bool = False
    eligible_for_warning: bool = False

    def __post_init__(self) -> None:
        """Reject any in-memory attempt to relax the query-only boundary."""

        _require_hard_query_model_flags(
            self.query_model_only,
            self.eligible_for_decision_layer,
            self.eligible_for_fpps,
            self.eligible_for_warning,
        )

    def predict_probabilities(self, frame: pd.DataFrame) -> pd.Series:
        """Return positive-class query scores from the fitted challenger."""

        values = _validated_prediction_matrix(frame, self.feature_order)
        predict_proba = getattr(self.estimator, "predict_proba", None)
        if predict_proba is None:
            raise QueryModelError("boosted estimator does not expose predict_proba.")
        probabilities = predict_proba(values)
        if getattr(probabilities, "ndim", None) != 2 or probabilities.shape[1] != 2:
            raise QueryModelError(
                "boosted estimator must return two-class probabilities."
            )
        return pd.Series(
            probabilities[:, 1],
            index=frame.index,
            name="query_probability_0_1",
            dtype="float64",
        )

    def to_manifest(self) -> dict[str, object]:
        """Return challenger lineage, fitted parameters, and hard safety gates."""

        get_params = getattr(self.estimator, "get_params", None)
        parameters = get_params(deep=False) if get_params is not None else {}
        if parameters.get("early_stopping") is not False:
            raise QueryModelError(
                "boosted query models must retain early_stopping=False."
            )
        return {
            "model_id": self.model_id,
            "model_family": self.model_family,
            "feature_order": list(self.feature_order),
            "feature_schema_version": self.feature_schema_version,
            "labelset_version": self.labelset_version,
            "trained_at_utc": self.trained_at_utc,
            "training_rows": self.training_rows,
            "positive_rows": self.positive_rows,
            "negative_rows": self.negative_rows,
            "estimator_parameters": _json_safe_mapping(parameters),
            **_safety_manifest(),
            "warning": QUERY_MODEL_WARNING,
        }


def train_logistic_query_model(
    frame: pd.DataFrame,
    *,
    feature_order: Sequence[str],
    label_column: str,
    model_id: str,
    feature_schema_version: str,
    labelset_version: str,
    epochs: int = 1_000,
    learning_rate: float = 0.08,
    l2: float = 0.001,
    balanced_class_weights: bool = True,
    trained_at_utc: str | None = None,
) -> LogisticQueryModel:
    """Fit a dependency-light logistic baseline on explicit reviewed labels."""

    import numpy as np

    _validate_training_parameters(epochs, learning_rate, l2)
    metadata = _validated_metadata(
        model_id=model_id,
        feature_schema_version=feature_schema_version,
        labelset_version=labelset_version,
    )
    features, labels, order = _validated_training_data(
        frame,
        feature_order=feature_order,
        feature_schema_version=metadata["feature_schema_version"],
        label_column=label_column,
    )
    means = features.mean(axis=0)
    scales = features.std(axis=0)
    scales = np.where(scales == 0.0, 1.0, scales)
    standardised = (features - means) / scales
    design = np.column_stack([np.ones(len(standardised)), standardised])
    weights = np.zeros(design.shape[1], dtype=float)
    if balanced_class_weights:
        positive_count = float(labels.sum())
        negative_count = float(len(labels) - positive_count)
        sample_weights = np.where(
            labels == 1,
            len(labels) / (2.0 * positive_count),
            len(labels) / (2.0 * negative_count),
        )
        sample_weights = sample_weights / sample_weights.mean()
    else:
        sample_weights = np.ones(len(labels), dtype=float)
    for _epoch in range(epochs):
        logits = np.clip(design @ weights, -40.0, 40.0)
        probabilities = 1.0 / (1.0 + np.exp(-logits))
        errors = (probabilities - labels) * sample_weights
        gradient = (design.T @ errors) / len(labels)
        gradient[1:] += l2 * weights[1:]
        weights -= learning_rate * gradient
    timestamp = trained_at_utc or _utc_now()
    if not str(timestamp).strip():
        raise QueryModelError("trained_at_utc must not be blank.")
    return LogisticQueryModel(
        model_id=metadata["model_id"],
        feature_order=order,
        feature_means=tuple(float(value) for value in means),
        feature_scales=tuple(float(value) for value in scales),
        coefficients=tuple(float(value) for value in weights[1:]),
        intercept=float(weights[0]),
        feature_schema_version=metadata["feature_schema_version"],
        labelset_version=metadata["labelset_version"],
        trained_at_utc=str(timestamp),
        training_rows=len(labels),
        positive_rows=int(labels.sum()),
        negative_rows=int(len(labels) - labels.sum()),
        epochs=epochs,
        learning_rate=float(learning_rate),
        l2=float(l2),
        balanced_class_weights=bool(balanced_class_weights),
    )


def train_hist_gradient_boosting_query_model(
    frame: pd.DataFrame,
    *,
    feature_order: Sequence[str],
    label_column: str,
    model_id: str,
    feature_schema_version: str,
    labelset_version: str,
    random_state: int = 0,
    estimator_parameters: Mapping[str, object] | None = None,
    trained_at_utc: str | None = None,
) -> HistGradientBoostingQueryModel:
    """Fit the optional shallow challenger with ``early_stopping=False``.

    scikit-learn is loaded only when this function is called. Install the
    project with the ``ml`` extra if the dependency error is raised.
    """

    module = _load_sklearn_ensemble()
    estimator_class = getattr(module, "HistGradientBoostingClassifier", None)
    if estimator_class is None:
        raise QueryModelDependencyError(
            "scikit-learn does not provide HistGradientBoostingClassifier; "
            "install a supported version with `pip install -e .[ml]`."
        )
    metadata = _validated_metadata(
        model_id=model_id,
        feature_schema_version=feature_schema_version,
        labelset_version=labelset_version,
    )
    features, labels, order = _validated_training_data(
        frame,
        feature_order=feature_order,
        feature_schema_version=metadata["feature_schema_version"],
        label_column=label_column,
    )
    parameters: dict[str, object] = {
        "learning_rate": 0.08,
        "max_iter": 150,
        "max_leaf_nodes": 15,
        "min_samples_leaf": 10,
        "l2_regularization": 0.1,
        "early_stopping": False,
        "random_state": random_state,
    }
    supplied = dict(estimator_parameters or {})
    if supplied.get("early_stopping") not in (None, False):
        raise QueryModelError(
            "early_stopping must be False; query models may not create an "
            "internal random validation split."
        )
    supplied["early_stopping"] = False
    parameters.update(supplied)
    estimator = estimator_class(**parameters)
    sample_weights = _balanced_sample_weights(labels)
    estimator.fit(features, labels, sample_weight=sample_weights)
    return HistGradientBoostingQueryModel(
        estimator=estimator,
        model_id=metadata["model_id"],
        feature_order=order,
        feature_schema_version=metadata["feature_schema_version"],
        labelset_version=metadata["labelset_version"],
        trained_at_utc=str(trained_at_utc or _utc_now()),
        training_rows=len(labels),
        positive_rows=int(labels.sum()),
        negative_rows=int(len(labels) - labels.sum()),
    )


def save_logistic_query_model(
    model: LogisticQueryModel,
    model_path: str | Path,
    *,
    manifest_path: str | Path | None = None,
) -> QueryModelArtifacts:
    """Persist a logistic artifact plus a checksum-bearing sidecar manifest."""

    if not isinstance(model, LogisticQueryModel):
        raise QueryModelError("only LogisticQueryModel can use JSON persistence.")
    artifact_path = Path(model_path)
    if artifact_path.suffix.lower() != ".json":
        raise QueryModelError("logistic query-model artifact must be JSON.")
    sidecar_path = (
        Path(manifest_path)
        if manifest_path is not None
        else artifact_path.with_name(f"{artifact_path.stem}.manifest.json")
    )
    if sidecar_path.suffix.lower() != ".json":
        raise QueryModelError("logistic query-model manifest must be JSON.")
    if artifact_path.resolve() == sidecar_path.resolve():
        raise QueryModelError("model artifact and manifest paths must differ.")
    artifact_text = _json_text(model.to_artifact())
    artifact_bytes = artifact_text.encode("utf-8")
    artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
    manifest = {
        **model.to_manifest(),
        "artifact_file": artifact_path.name,
        "artifact_schema": LOGISTIC_ARTIFACT_SCHEMA,
        "artifact_sha256": artifact_sha256,
    }
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(artifact_bytes)
    sidecar_path.write_text(_json_text(manifest), encoding="utf-8")
    return QueryModelArtifacts(model=artifact_path, manifest=sidecar_path)


def load_logistic_query_model(
    model_path: str | Path,
    *,
    manifest_path: str | Path | None = None,
    verify_manifest: bool = True,
) -> LogisticQueryModel:
    """Reload a logistic artifact and verify its sidecar checksum by default."""

    artifact_path = Path(model_path)
    try:
        artifact_bytes = artifact_path.read_bytes()
        artifact = json.loads(artifact_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise QueryModelError(f"could not read query-model artifact: {exc}") from exc
    if not isinstance(artifact, dict):
        raise QueryModelError("query-model artifact must contain a JSON object.")
    model = _model_from_artifact(artifact)
    sidecar_path = (
        Path(manifest_path)
        if manifest_path is not None
        else artifact_path.with_name(f"{artifact_path.stem}.manifest.json")
    )
    if verify_manifest:
        if not sidecar_path.exists():
            raise QueryModelError(
                f"query-model manifest is required but missing: {sidecar_path}"
            )
        try:
            manifest = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise QueryModelError(f"could not read query-model manifest: {exc}") from exc
        if not isinstance(manifest, dict):
            raise QueryModelError("query-model manifest must contain a JSON object.")
        expected_hash = manifest.get("artifact_sha256")
        actual_hash = hashlib.sha256(artifact_bytes).hexdigest()
        if expected_hash != actual_hash:
            raise QueryModelError("query-model artifact checksum does not match manifest.")
        if manifest.get("model_id") != model.model_id:
            raise QueryModelError("query-model artifact and manifest model_id differ.")
        _validate_safety_mapping(manifest)
    return model


def _model_from_artifact(artifact: Mapping[str, object]) -> LogisticQueryModel:
    if artifact.get("artifact_schema") != LOGISTIC_ARTIFACT_SCHEMA:
        raise QueryModelError("unsupported logistic query-model artifact schema.")
    if artifact.get("model_family") != "logistic_regression_from_scratch":
        raise QueryModelError("artifact is not a logistic query model.")
    safety = _mapping(artifact.get("safety"), "safety")
    _validate_safety_mapping(safety)
    feature_schema_version = _non_blank(
        artifact.get("feature_schema_version"),
        "feature_schema_version",
    )
    feature_order = _validated_schema_feature_order(
        _string_tuple(artifact.get("feature_order"), "feature_order"),
        feature_schema_version,
    )
    scaler = _mapping(artifact.get("scaler"), "scaler")
    if scaler.get("kind") != "standard":
        raise QueryModelError("logistic query model requires a standard scaler.")
    means = _feature_mapping(scaler.get("means"), feature_order, "scaler means")
    scales = _feature_mapping(scaler.get("scales"), feature_order, "scaler scales")
    if any(value <= 0.0 for value in scales):
        raise QueryModelError("all persisted feature scales must be positive.")
    coefficient_block = _mapping(artifact.get("coefficients"), "coefficients")
    coefficients = _feature_mapping(
        coefficient_block.get("standardised_feature_coefficients"),
        feature_order,
        "feature coefficients",
    )
    intercept = _finite_float(coefficient_block.get("intercept"), "intercept")
    training = _mapping(artifact.get("training"), "training")
    training_rows = _positive_int(training.get("rows"), "training rows")
    positive_rows = _positive_int(training.get("positive_rows"), "positive rows")
    negative_rows = _positive_int(training.get("negative_rows"), "negative rows")
    if positive_rows + negative_rows != training_rows:
        raise QueryModelError("persisted training class counts do not sum to rows.")
    return LogisticQueryModel(
        model_id=_non_blank(artifact.get("model_id"), "model_id"),
        feature_order=feature_order,
        feature_means=means,
        feature_scales=scales,
        coefficients=coefficients,
        intercept=intercept,
        feature_schema_version=feature_schema_version,
        labelset_version=_non_blank(
            artifact.get("labelset_version"),
            "labelset_version",
        ),
        trained_at_utc=_non_blank(artifact.get("trained_at_utc"), "trained_at_utc"),
        training_rows=training_rows,
        positive_rows=positive_rows,
        negative_rows=negative_rows,
        epochs=_positive_int(training.get("epochs"), "epochs"),
        learning_rate=_positive_float(
            training.get("learning_rate"),
            "learning_rate",
        ),
        l2=_non_negative_float(training.get("l2"), "l2"),
        balanced_class_weights=_strict_bool(
            training.get("balanced_class_weights"),
            "balanced_class_weights",
        ),
    )


def _validated_training_data(
    frame: pd.DataFrame,
    *,
    feature_order: Sequence[str],
    feature_schema_version: str,
    label_column: str,
) -> tuple[object, object, tuple[str, ...]]:
    import numpy as np

    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise QueryModelError("training frame must be a non-empty pandas DataFrame.")
    order = _validated_schema_feature_order(
        _validated_feature_order(feature_order),
        feature_schema_version,
    )
    label_name = _non_blank(label_column, "label_column")
    missing = [column for column in (*order, label_name) if column not in frame.columns]
    if missing:
        raise QueryModelError(
            f"training frame is missing required columns: {', '.join(missing)}"
        )
    numeric = frame.loc[:, list(order)].apply(pd.to_numeric, errors="coerce")
    values = numeric.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise QueryModelError("training features must be finite numeric values.")
    labels_numeric = pd.to_numeric(frame[label_name], errors="coerce")
    if labels_numeric.isna().any():
        raise QueryModelError("training labels must be numeric 0/1 values.")
    labels_float = labels_numeric.to_numpy(dtype=float)
    if not np.isfinite(labels_float).all() or not np.isin(labels_float, [0.0, 1.0]).all():
        raise QueryModelError(
            "training labels must contain only explicit reviewed 0/1 values; "
            "uncertain, unobservable, and unreviewed cells must be excluded."
        )
    labels = labels_float.astype(int)
    if set(labels.tolist()) != {0, 1}:
        raise QueryModelError("training labels must contain both explicit classes.")
    return values, labels, order


def _validated_prediction_matrix(
    frame: pd.DataFrame,
    feature_order: Sequence[str],
) -> object:
    import numpy as np

    if not isinstance(frame, pd.DataFrame):
        raise QueryModelError("prediction input must be a pandas DataFrame.")
    missing = [column for column in feature_order if column not in frame.columns]
    if missing:
        raise QueryModelError(
            f"prediction frame is missing model features: {', '.join(missing)}"
        )
    numeric = frame.loc[:, list(feature_order)].apply(pd.to_numeric, errors="coerce")
    values = numeric.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise QueryModelError("prediction features must be finite numeric values.")
    return values


def _validated_feature_order(feature_order: Sequence[str]) -> tuple[str, ...]:
    if isinstance(feature_order, (str, bytes)) or not feature_order:
        raise QueryModelError("feature_order must contain at least one feature name.")
    order = tuple(_non_blank(value, "feature name") for value in feature_order)
    if len(set(order)) != len(order):
        raise QueryModelError("feature_order must not contain duplicate names.")
    return order


def _validated_metadata(
    *,
    model_id: str,
    feature_schema_version: str,
    labelset_version: str,
) -> dict[str, str]:
    metadata = {
        "model_id": _non_blank(model_id, "model_id"),
        "feature_schema_version": _non_blank(
            feature_schema_version,
            "feature_schema_version",
        ),
        "labelset_version": _non_blank(labelset_version, "labelset_version"),
    }
    try:
        get_feature_schema(metadata["feature_schema_version"])
    except FeatureSchemaError as exc:
        raise QueryModelError(str(exc)) from exc
    return metadata


def _validated_schema_feature_order(
    feature_order: Sequence[str],
    feature_schema_version: str,
) -> tuple[str, ...]:
    try:
        schema = get_feature_schema(feature_schema_version)
        schema_order = schema.validate_columns(feature_order, allow_extra=False)
    except FeatureSchemaError as exc:
        raise QueryModelError(str(exc)) from exc
    order = tuple(feature_order)
    if schema_order != order:
        raise QueryModelError(
            f"feature_order must follow schema {feature_schema_version!r}: "
            f"{', '.join(schema_order)}."
        )
    return order


def _validate_training_parameters(
    epochs: int,
    learning_rate: float,
    l2: float,
) -> None:
    _positive_int(epochs, "epochs")
    _positive_float(learning_rate, "learning_rate")
    _non_negative_float(l2, "l2")


def _balanced_sample_weights(labels: object) -> object:
    import numpy as np

    values = np.asarray(labels, dtype=int)
    positive_count = float(values.sum())
    negative_count = float(len(values) - positive_count)
    weights = np.where(
        values == 1,
        len(values) / (2.0 * positive_count),
        len(values) / (2.0 * negative_count),
    )
    return weights / weights.mean()


def _load_sklearn_ensemble() -> object:
    try:
        return importlib.import_module("sklearn.ensemble")
    except (ImportError, ModuleNotFoundError) as exc:
        raise QueryModelDependencyError(
            "HistGradientBoosting query model requires optional scikit-learn; "
            "install it with `pip install -e .[ml]`."
        ) from exc


def _safety_manifest() -> dict[str, bool | str]:
    return QUERY_MODEL_ELIGIBILITY.as_manifest_fields()


def _require_hard_query_model_flags(
    query_model_only: object,
    eligible_for_decision_layer: object,
    eligible_for_fpps: object,
    eligible_for_warning: object,
) -> None:
    observed = {
        "query_model_only": query_model_only,
        "eligible_for_decision_layer": eligible_for_decision_layer,
        "eligible_for_fpps": eligible_for_fpps,
        "eligible_for_warning": eligible_for_warning,
    }
    expected = {
        "query_model_only": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }
    mismatches = [
        field
        for field, required in expected.items()
        if type(observed[field]) is not bool or observed[field] is not required
    ]
    if mismatches:
        raise QueryModelError(
            "query-model in-memory safety fields are immutable: "
            + ", ".join(mismatches)
            + "."
        )


def _validate_safety_mapping(mapping: Mapping[str, object]) -> None:
    expected = _safety_manifest()
    for field, expected_value in expected.items():
        actual_value = mapping.get(field)
        matches = (
            actual_value is expected_value
            if isinstance(expected_value, bool)
            else actual_value == expected_value
        )
        if not matches:
            raise QueryModelError(
                f"query-model safety field {field} must remain {expected_value}."
            )


def _feature_mapping(
    value: object,
    feature_order: Sequence[str],
    label: str,
) -> tuple[float, ...]:
    mapping = _mapping(value, label)
    if set(mapping) != set(feature_order):
        raise QueryModelError(f"{label} keys must exactly match feature_order.")
    return tuple(_finite_float(mapping[feature], label) for feature in feature_order)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise QueryModelError(f"{label} must be a JSON object.")
    return value


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or not value:
        raise QueryModelError(f"{label} must be a non-empty list of strings.")
    result = tuple(_non_blank(item, label) for item in value)
    if len(set(result)) != len(result):
        raise QueryModelError(f"{label} contains duplicates.")
    return result


def _strict_bool(value: object, label: str) -> bool:
    if value is not True and value is not False:
        raise QueryModelError(f"{label} must be a JSON boolean.")
    return bool(value)


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise QueryModelError(f"{label} must be a positive integer.")
    return value


def _positive_float(value: object, label: str) -> float:
    numeric = _finite_float(value, label)
    if numeric <= 0.0:
        raise QueryModelError(f"{label} must be positive.")
    return numeric


def _non_negative_float(value: object, label: str) -> float:
    numeric = _finite_float(value, label)
    if numeric < 0.0:
        raise QueryModelError(f"{label} must be non-negative.")
    return numeric


def _finite_float(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise QueryModelError(f"{label} must be numeric, not boolean.")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise QueryModelError(f"{label} must be numeric.") from exc
    if not math.isfinite(numeric):
        raise QueryModelError(f"{label} must be finite.")
    return numeric


def _non_blank(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QueryModelError(f"{label} must be a non-blank string.")
    return value.strip()


def _json_safe_mapping(mapping: Mapping[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in mapping.items():
        if value is None or isinstance(value, (str, int, float, bool)):
            result[str(key)] = value
        else:
            result[str(key)] = repr(value)
    return result


def _json_text(value: Mapping[str, object]) -> str:
    try:
        return json.dumps(
            value,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        ) + "\n"
    except (TypeError, ValueError) as exc:
        raise QueryModelError(f"query-model metadata is not JSON serialisable: {exc}") from exc


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
