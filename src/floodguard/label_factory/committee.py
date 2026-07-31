"""Strict spatially grouped query-committee orchestration.

This module trains two *query-ranking* models: the repository's auditable
logistic baseline and an optional shallow histogram gradient-boosted
challenger.  Their scores may prioritise regions for blinded human review.
They do not create flood truth and can never feed FloodGuard decisions, FPPS,
action classes, or warnings.

The orchestration is intentionally stricter than the low-level model helpers.
It accepts only explicit human-reviewed/adjudicated binary targets from the
``training_and_query_pool`` role, produces repeated spatial-group out-of-fold
scores, and persists only the executable logistic model.  The boosted model is
represented by a non-executable audit manifest so arbitrary estimator pickles
never enter the label-factory artifact chain.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

import pandas as pd

from floodguard.label_factory.contracts import DatasetRole, QUERY_MODEL_ELIGIBILITY
from floodguard.label_factory.feature_schema import (
    FeatureSchemaError,
    get_feature_schema,
)
from floodguard.label_factory.query_models import (
    HistGradientBoostingQueryModel,
    LogisticQueryModel,
    QueryModelDependencyError,
    QueryModelError,
    save_logistic_query_model,
    train_hist_gradient_boosting_query_model,
    train_logistic_query_model,
)
from floodguard.label_factory.sampling import (
    absolute_probability_disagreement,
    jensen_shannon_disagreement,
    normalized_binary_entropy,
)
from floodguard.label_factory.training_join import (
    TrainingJoinError,
    VerifiedTrainingDerivation,
    verify_training_derivation,
)


COMMITTEE_RUN_SCHEMA = "floodguard.query_committee_run.v1"
BOOSTED_MANIFEST_SCHEMA = "floodguard.boosted_query_model_manifest.v1"
ALLOWED_LABEL_SOURCE_TYPES = frozenset({"human_reviewed", "human_adjudicated"})
QUERY_POOL_ROLE = DatasetRole.TRAINING_AND_QUERY_POOL.value
QUERY_COMMITTEE_WARNING = (
    "Query-committee scores prioritise blinded human review only. They are not "
    "flood truth and are ineligible for the decision layer, FPPS, action "
    "classes, and warnings."
)

_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*")
_TRAINING_METADATA_COLUMNS = (
    "sample_id",
    "query_region_id",
    "dataset_role",
    "label_source_type",
    "eligible_for_query_model_training",
    "labelset_version",
    "labelset_manifest_sha256",
)
_POOL_METADATA_COLUMNS = (
    "sample_id",
    "query_region_id",
    "dataset_role",
)


class CommitteeError(ValueError):
    """Raised when committee inputs, folds, or artifacts fail closed."""


class CommitteeDependencyError(RuntimeError):
    """Raised when the explicitly requested optional ML dependency is absent."""


@dataclass(frozen=True)
class SpatialGroupFold:
    """One deterministic validation-group assignment in a repeated split."""

    repeat_index: int
    fold_index: int
    validation_groups: tuple[str, ...]
    training_rows: int
    validation_rows: int


@dataclass(frozen=True)
class QueryCommitteeResult:
    """In-memory committee models, scores, and immutable run metadata."""

    run_id: str
    trained_at_utc: str
    feature_schema_version: str
    feature_order: tuple[str, ...]
    labelset_version: str
    labelset_manifest_sha256: str
    target_column: str
    group_column: str
    n_splits: int
    n_repeats: int
    random_seed: int
    folds: tuple[SpatialGroupFold, ...]
    logistic_model: LogisticQueryModel
    boosted_model: HistGradientBoostingQueryModel
    oof_scores: pd.DataFrame
    pool_scores: pd.DataFrame
    training_rows_sha256: str
    pool_rows_sha256: str
    feature_schema_sha256: str


@dataclass(frozen=True)
class CommitteeOutputPaths:
    """Paths atomically written for one query-committee run."""

    logistic_model: Path
    logistic_manifest: Path
    boosted_manifest: Path
    oof_scores: Path
    pool_scores: Path
    run_manifest: Path

    def as_dict(self) -> dict[str, Path]:
        """Return stable labels suitable for CLI output."""

        return {
            "logistic_model": self.logistic_model,
            "logistic_manifest": self.logistic_manifest,
            "boosted_manifest": self.boosted_manifest,
            "oof_scores": self.oof_scores,
            "pool_scores": self.pool_scores,
            "run_manifest": self.run_manifest,
        }


def make_repeated_spatial_group_folds(
    frame: pd.DataFrame,
    *,
    group_column: str = "spatial_group_id",
    target_column: str = "binary_target",
    n_splits: int = 5,
    n_repeats: int = 3,
    random_seed: int = 0,
) -> tuple[SpatialGroupFold, ...]:
    """Build deterministic repeated folds without ever splitting a group.

    Groups are ordered by a stable SHA-256 key for each repeat and greedily
    assigned to the currently smallest fold.  This keeps row counts reasonably
    balanced while ensuring repeated calls with identical inputs and settings
    produce identical assignments.  Every training complement is checked for
    both explicit binary classes before any model is fitted.
    """

    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise CommitteeError("fold input must be a non-empty pandas DataFrame.")
    group_name = _non_blank(group_column, "group_column")
    target_name = _non_blank(target_column, "target_column")
    _positive_int(n_splits, "n_splits", minimum=2)
    _positive_int(n_repeats, "n_repeats")
    if isinstance(random_seed, bool) or not isinstance(random_seed, int):
        raise CommitteeError("random_seed must be an integer.")
    missing = [name for name in (group_name, target_name) if name not in frame]
    if missing:
        raise CommitteeError(
            "fold input is missing required columns: " + ", ".join(missing) + "."
        )
    groups = _validated_identifier_series(frame[group_name], group_name, unique=False)
    targets = _validated_binary_target(frame[target_name], target_name)
    distinct_groups = sorted(set(groups))
    if len(distinct_groups) < n_splits:
        raise CommitteeError(
            f"n_splits={n_splits} requires at least {n_splits} spatial groups; "
            f"found {len(distinct_groups)}."
        )
    group_sizes = pd.Series(groups).value_counts().to_dict()
    folds: list[SpatialGroupFold] = []
    # Use a fresh positional index so caller-supplied duplicate DataFrame
    # indices cannot affect masking or fold coverage.
    group_series = pd.Series(groups)
    target_series = pd.Series(targets)
    for repeat_zero in range(n_repeats):
        ordered = sorted(
            distinct_groups,
            key=lambda group: (
                _stable_hash_key(random_seed, repeat_zero, group),
                -int(group_sizes[group]),
                group,
            ),
        )
        buckets: list[list[str]] = [[] for _ in range(n_splits)]
        bucket_rows = [0] * n_splits
        for group in ordered:
            fold_zero = min(
                range(n_splits),
                key=lambda index: (bucket_rows[index], index),
            )
            buckets[fold_zero].append(group)
            bucket_rows[fold_zero] += int(group_sizes[group])
        assigned = [group for bucket in buckets for group in bucket]
        if sorted(assigned) != distinct_groups or len(assigned) != len(set(assigned)):
            raise CommitteeError("internal error: a spatial group was lost or split.")
        for fold_zero, validation_groups in enumerate(buckets):
            validation_mask = group_series.isin(validation_groups)
            training_mask = ~validation_mask
            if not validation_mask.any() or not training_mask.any():
                raise CommitteeError(
                    f"repeat {repeat_zero + 1}, fold {fold_zero + 1} is empty."
                )
            training_classes = set(target_series.loc[training_mask].astype(int).tolist())
            if training_classes != {0, 1}:
                raise CommitteeError(
                    "spatial grouping creates a one-class training complement at "
                    f"repeat {repeat_zero + 1}, fold {fold_zero + 1}; groups "
                    f"{sorted(validation_groups)!r} must not be used for model "
                    "fitting until the grouping or reviewed-label coverage is fixed."
                )
            folds.append(
                SpatialGroupFold(
                    repeat_index=repeat_zero + 1,
                    fold_index=fold_zero + 1,
                    validation_groups=tuple(sorted(validation_groups)),
                    training_rows=int(training_mask.sum()),
                    validation_rows=int(validation_mask.sum()),
                )
            )
    return tuple(folds)


def train_query_committee(
    training_frame: pd.DataFrame,
    pool_frame: pd.DataFrame,
    *,
    labelset_version: str,
    labelset_manifest_sha256: str,
    feature_schema_version: str = "sar_change_v2",
    feature_order: Sequence[str] | None = None,
    target_column: str = "binary_target",
    group_column: str = "spatial_group_id",
    n_splits: int = 5,
    n_repeats: int = 3,
    random_seed: int = 0,
    run_id: str | None = None,
    trained_at_utc: str | None = None,
    logistic_epochs: int = 1_000,
    logistic_learning_rate: float = 0.08,
    logistic_l2: float = 0.001,
    boosted_parameters: Mapping[str, object] | None = None,
) -> QueryCommitteeResult:
    """Train the strict query committee and generate OOF plus pool scores."""

    labelset = _stable_identifier(labelset_version, "labelset_version")
    labelset_hash = _sha256_text(
        labelset_manifest_sha256,
        "labelset_manifest_sha256",
    )
    schema_version = _stable_identifier(
        feature_schema_version, "feature_schema_version"
    )
    target_name = _non_blank(target_column, "target_column")
    group_name = _non_blank(group_column, "group_column")
    timestamp = _validated_timestamp(trained_at_utc)
    resolved_run_id = (
        _stable_identifier(run_id, "run_id")
        if run_id is not None
        else "query-committee-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    )
    order = _resolve_feature_order(schema_version, feature_order)
    training = _validate_training_frame(
        training_frame,
        feature_order=order,
        labelset_version=labelset,
        labelset_manifest_sha256=labelset_hash,
        target_column=target_name,
        group_column=group_name,
    )
    pool = _validate_pool_frame(
        pool_frame,
        feature_order=order,
        feature_schema_version=schema_version,
        labelset_version=labelset,
        labelset_manifest_sha256=labelset_hash,
    )
    shared_samples = sorted(set(training["sample_id"]).intersection(pool["sample_id"]))
    if shared_samples:
        preview = ", ".join(shared_samples[:5])
        raise CommitteeError(
            "reviewed training samples must not remain in the unreviewed query "
            f"pool; overlapping sample_id values include: {preview}."
        )
    shared_queries = sorted(
        set(training["query_region_id"]).intersection(pool["query_region_id"])
    )
    if shared_queries:
        preview = ", ".join(shared_queries[:5])
        raise CommitteeError(
            "reviewed training queries must not remain in the unreviewed query "
            f"pool; overlapping query_region_id values include: {preview}."
        )
    folds = make_repeated_spatial_group_folds(
        training,
        group_column=group_name,
        target_column=target_name,
        n_splits=n_splits,
        n_repeats=n_repeats,
        random_seed=random_seed,
    )

    oof_parts: list[pd.DataFrame] = []
    for fold in folds:
        validation_mask = training[group_name].isin(fold.validation_groups)
        fold_training = training.loc[~validation_mask].copy()
        fold_validation = training.loc[validation_mask].copy()
        model_suffix = f"r{fold.repeat_index:02d}-f{fold.fold_index:02d}"
        logistic = _train_logistic(
            fold_training,
            feature_order=order,
            target_column=target_name,
            model_id=f"{resolved_run_id}-logistic-{model_suffix}",
            feature_schema_version=schema_version,
            labelset_version=labelset,
            trained_at_utc=timestamp,
            epochs=logistic_epochs,
            learning_rate=logistic_learning_rate,
            l2=logistic_l2,
        )
        boosted = _train_boosted(
            fold_training,
            feature_order=order,
            target_column=target_name,
            model_id=f"{resolved_run_id}-boosted-{model_suffix}",
            feature_schema_version=schema_version,
            labelset_version=labelset,
            trained_at_utc=timestamp,
            random_seed=random_seed + fold.repeat_index * 10_000 + fold.fold_index,
            parameters=boosted_parameters,
        )
        part = _score_frame(
            fold_validation,
            logistic=logistic,
            boosted=boosted,
            include_target=target_name,
            preserve_input_columns=False,
        )
        part.insert(0, "fold_index", fold.fold_index)
        part.insert(0, "repeat_index", fold.repeat_index)
        part["spatial_group_column"] = group_name
        part["spatial_group_id"] = fold_validation[group_name].to_numpy()
        oof_parts.append(part)

    oof_scores = pd.concat(oof_parts, ignore_index=True)
    oof_scores = oof_scores.sort_values(
        ["repeat_index", "sample_id"], kind="stable"
    ).reset_index(drop=True)
    expected_oof_rows = len(training) * n_repeats
    if len(oof_scores) != expected_oof_rows:
        raise CommitteeError(
            f"OOF coverage must be exactly {expected_oof_rows} rows; "
            f"generated {len(oof_scores)}."
        )
    coverage = oof_scores.groupby(["repeat_index", "sample_id"], sort=False).size()
    if not (coverage == 1).all():
        raise CommitteeError("every sample must receive exactly one OOF score per repeat.")

    full_logistic = _train_logistic(
        training,
        feature_order=order,
        target_column=target_name,
        model_id=f"{resolved_run_id}-logistic-full",
        feature_schema_version=schema_version,
        labelset_version=labelset,
        trained_at_utc=timestamp,
        epochs=logistic_epochs,
        learning_rate=logistic_learning_rate,
        l2=logistic_l2,
    )
    full_boosted = _train_boosted(
        training,
        feature_order=order,
        target_column=target_name,
        model_id=f"{resolved_run_id}-boosted-full",
        feature_schema_version=schema_version,
        labelset_version=labelset,
        trained_at_utc=timestamp,
        random_seed=random_seed,
        parameters=boosted_parameters,
    )
    pool_scores = _score_frame(
        pool,
        logistic=full_logistic,
        boosted=full_boosted,
        include_target=None,
        preserve_input_columns=True,
    ).sort_values("sample_id", kind="stable").reset_index(drop=True)
    oof_scores["labelset_manifest_sha256"] = labelset_hash
    pool_scores["labelset_manifest_sha256"] = labelset_hash

    return QueryCommitteeResult(
        run_id=resolved_run_id,
        trained_at_utc=timestamp,
        feature_schema_version=schema_version,
        feature_order=order,
        labelset_version=labelset,
        labelset_manifest_sha256=labelset_hash,
        target_column=target_name,
        group_column=group_name,
        n_splits=n_splits,
        n_repeats=n_repeats,
        random_seed=random_seed,
        folds=folds,
        logistic_model=full_logistic,
        boosted_model=full_boosted,
        oof_scores=oof_scores,
        pool_scores=pool_scores,
        training_rows_sha256=_frame_sha256(training),
        pool_rows_sha256=_frame_sha256(pool),
        feature_schema_sha256=_feature_schema_sha256(schema_version),
    )


def train_and_write_query_committee(
    training_csv: str | Path,
    pool_csv: str | Path,
    output_directory: str | Path,
    *,
    training_derivation_manifest: str | Path,
    release_validation_receipt: str | Path,
    labelset_manifest: str | Path,
    **training_options: Any,
) -> CommitteeOutputPaths:
    """Verify derivation provenance, train, then atomically write a new run."""

    output = Path(output_directory)
    _require_new_output_directory(output)
    training_path = _existing_csv(training_csv, "training")
    pool_path = _existing_csv(pool_csv, "pool")
    try:
        verified_derivation = verify_training_derivation(
            training_path,
            training_derivation_manifest,
            release_validation_receipt,
            labelset_manifest,
        )
    except TrainingJoinError as exc:
        raise CommitteeError(
            f"training derivation provenance failed validation: {exc}"
        ) from exc
    supplied_labelset_version = training_options.get("labelset_version")
    if supplied_labelset_version not in (None, verified_derivation.labelset_id):
        raise CommitteeError(
            "requested labelset_version differs from the verified training derivation."
        )
    supplied_labelset_hash = training_options.get("labelset_manifest_sha256")
    if supplied_labelset_hash not in (
        None,
        verified_derivation.labelset_manifest_sha256,
    ):
        raise CommitteeError(
            "requested labelset_manifest_sha256 differs from the verified training derivation."
        )
    training_options["labelset_version"] = verified_derivation.labelset_id
    training_options["labelset_manifest_sha256"] = (
        verified_derivation.labelset_manifest_sha256
    )
    training_source_sha256 = _file_sha256(training_path)
    pool_source_sha256 = _file_sha256(pool_path)
    try:
        training_frame = pd.read_csv(training_path)
        pool_frame = pd.read_csv(pool_path)
    except (OSError, UnicodeError, pd.errors.ParserError) as exc:
        raise CommitteeError(f"could not read committee CSV input: {exc}") from exc
    result = train_query_committee(training_frame, pool_frame, **training_options)
    if _file_sha256(training_path) != training_source_sha256:
        raise CommitteeError("training CSV changed while the committee run was active.")
    if _file_sha256(pool_path) != pool_source_sha256:
        raise CommitteeError("pool CSV changed while the committee run was active.")
    try:
        verified_after_training = verify_training_derivation(
            training_path,
            training_derivation_manifest,
            release_validation_receipt,
            labelset_manifest,
        )
    except TrainingJoinError as exc:
        raise CommitteeError(
            f"training derivation changed while the committee run was active: {exc}"
        ) from exc
    if verified_after_training != verified_derivation:
        raise CommitteeError(
            "training derivation provenance changed while the committee run was active."
        )
    return write_query_committee_outputs(
        result,
        output,
        training_source=training_path,
        pool_source=pool_path,
        verified_training_derivation=verified_derivation,
        provenance_sources={
            "training_derivation_manifest": Path(training_derivation_manifest),
            "release_validation_receipt": Path(release_validation_receipt),
            "labelset_manifest": Path(labelset_manifest),
        },
    )


def write_query_committee_outputs(
    result: QueryCommitteeResult,
    output_directory: str | Path,
    *,
    training_source: str | Path | None = None,
    pool_source: str | Path | None = None,
    verified_training_derivation: VerifiedTrainingDerivation | None = None,
    provenance_sources: Mapping[str, str | Path] | None = None,
) -> CommitteeOutputPaths:
    """Atomically persist all committee artifacts without overwriting anything."""

    if not isinstance(result, QueryCommitteeResult):
        raise CommitteeError("result must be a QueryCommitteeResult.")
    _validate_result_for_persistence(result)
    output = Path(output_directory)
    _require_new_output_directory(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=str(output.parent))
    )
    try:
        logistic_path = temporary / "logistic_query_model.json"
        logistic_manifest_path = temporary / "logistic_query_model.manifest.json"
        boosted_manifest_path = temporary / "boosted_query_model.manifest.json"
        oof_path = temporary / "grouped_oof_scores.csv"
        pool_path = temporary / "query_pool_scores.csv"
        run_manifest_path = temporary / "committee_run_manifest.json"

        save_logistic_query_model(
            result.logistic_model,
            logistic_path,
            manifest_path=logistic_manifest_path,
        )
        boosted_manifest = {
            "artifact_schema": BOOSTED_MANIFEST_SCHEMA,
            **result.boosted_model.to_manifest(),
            "persistence": "non_executable_manifest_only",
            "serialized_estimator": False,
            "warning": QUERY_COMMITTEE_WARNING,
        }
        _assert_no_cutoff_fields(boosted_manifest)
        boosted_manifest_path.write_text(
            _json_text(boosted_manifest), encoding="utf-8"
        )
        result.oof_scores.to_csv(oof_path, index=False, lineterminator="\n")
        result.pool_scores.to_csv(pool_path, index=False, lineterminator="\n")

        artifact_paths = (
            ("logistic_model", logistic_path),
            ("logistic_manifest", logistic_manifest_path),
            ("boosted_manifest", boosted_manifest_path),
            ("oof_scores", oof_path),
            ("pool_scores", pool_path),
        )
        manifest = _run_manifest(
            result,
            artifact_paths=artifact_paths,
            training_source=training_source,
            pool_source=pool_source,
            verified_training_derivation=verified_training_derivation,
            provenance_sources=provenance_sources,
        )
        _assert_no_cutoff_fields(manifest)
        run_manifest_path.write_text(_json_text(manifest), encoding="utf-8")

        if output.exists():
            raise CommitteeError(
                f"output directory appeared during the run and will not be overwritten: {output}"
            )
        temporary.rename(output)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise

    return CommitteeOutputPaths(
        logistic_model=output / "logistic_query_model.json",
        logistic_manifest=output / "logistic_query_model.manifest.json",
        boosted_manifest=output / "boosted_query_model.manifest.json",
        oof_scores=output / "grouped_oof_scores.csv",
        pool_scores=output / "query_pool_scores.csv",
        run_manifest=output / "committee_run_manifest.json",
    )


def _validate_training_frame(
    frame: pd.DataFrame,
    *,
    feature_order: tuple[str, ...],
    labelset_version: str,
    labelset_manifest_sha256: str,
    target_column: str,
    group_column: str,
) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise CommitteeError("training input must be a non-empty pandas DataFrame.")
    required = (*_TRAINING_METADATA_COLUMNS, group_column, target_column, *feature_order)
    _require_columns(frame, required, "training")
    result = frame.copy().reset_index(drop=True)
    result["sample_id"] = _validated_identifier_series(
        result["sample_id"], "sample_id", unique=True
    )
    result["query_region_id"] = _validated_identifier_series(
        result["query_region_id"], "query_region_id", unique=False
    )
    result[group_column] = _validated_identifier_series(
        result[group_column], group_column, unique=False
    )
    _require_single_group_per_query(result, group_column)
    roles = [_role_value(value) for value in result["dataset_role"]]
    invalid_roles = sorted({role for role in roles if role != QUERY_POOL_ROLE})
    if invalid_roles:
        raise CommitteeError(
            "query-model training accepts only dataset_role="
            f"{QUERY_POOL_ROLE!r}; rejected roles: {invalid_roles!r}."
        )
    result["dataset_role"] = roles
    invalid_sources = sorted(
        {
            str(value)
            for value in result["label_source_type"]
            if not isinstance(value, str) or value not in ALLOWED_LABEL_SOURCE_TYPES
        }
    )
    if invalid_sources:
        raise CommitteeError(
            "label_source_type must be human_reviewed or human_adjudicated; "
            f"rejected values: {invalid_sources!r}."
        )
    if not all(_is_literal_bool(value, expected=True) for value in result[
        "eligible_for_query_model_training"
    ]):
        raise CommitteeError(
            "eligible_for_query_model_training must be literal boolean true for "
            "every training row; truthy strings and integers are rejected."
        )
    if not all(
        isinstance(value, str) and value == labelset_version
        for value in result["labelset_version"]
    ):
        observed = sorted({str(value) for value in result["labelset_version"]})
        raise CommitteeError(
            f"every training row must match labelset_version={labelset_version!r}; "
            f"observed {observed!r}."
        )
    if not all(
        isinstance(value, str) and value == labelset_manifest_sha256
        for value in result["labelset_manifest_sha256"]
    ):
        raise CommitteeError(
            "every training row must match the frozen "
            f"labelset_manifest_sha256={labelset_manifest_sha256!r}."
        )
    result[target_column] = _validated_binary_target(result[target_column], target_column)
    if set(result[target_column].tolist()) != {0, 1}:
        raise CommitteeError("training input must contain both explicit binary classes.")
    _validate_finite_features(result, feature_order, "training")
    return result


def _validate_pool_frame(
    frame: pd.DataFrame,
    *,
    feature_order: tuple[str, ...],
    feature_schema_version: str,
    labelset_version: str,
    labelset_manifest_sha256: str,
) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise CommitteeError("pool input must be a non-empty pandas DataFrame.")
    _require_columns(frame, (*_POOL_METADATA_COLUMNS, *feature_order), "pool")
    result = frame.copy().reset_index(drop=True)
    result["sample_id"] = _validated_identifier_series(
        result["sample_id"], "sample_id", unique=True
    )
    result["query_region_id"] = _validated_identifier_series(
        result["query_region_id"], "query_region_id", unique=False
    )
    roles = [_role_value(value) for value in result["dataset_role"]]
    invalid_roles = sorted({role for role in roles if role != QUERY_POOL_ROLE})
    if invalid_roles:
        raise CommitteeError(
            "query scoring accepts only dataset_role="
            f"{QUERY_POOL_ROLE!r}; rejected roles: {invalid_roles!r}."
        )
    result["dataset_role"] = roles
    if "eligible_for_review_queue" in result and not all(
        _is_literal_bool(value, expected=True)
        for value in result["eligible_for_review_queue"]
    ):
        raise CommitteeError(
            "pool eligible_for_review_queue values must be literal boolean true."
        )
    expected_optional_safety = {
        "query_model_only": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }
    for column, expected in expected_optional_safety.items():
        if column in result and not all(
            _is_literal_bool(value, expected=expected) for value in result[column]
        ):
            raise CommitteeError(f"pool safety field {column} must remain {expected}.")
    if "feature_schema_version" in result and not all(
        isinstance(value, str) and value == feature_schema_version
        for value in result["feature_schema_version"]
    ):
        raise CommitteeError(
            "pool feature_schema_version does not match the requested model schema."
        )
    if "labelset_version" in result and not all(
        isinstance(value, str) and value == labelset_version
        for value in result["labelset_version"]
    ):
        raise CommitteeError(
            "pool labelset_version does not match the requested frozen labelset."
        )
    if "labelset_manifest_sha256" in result and not all(
        isinstance(value, str) and value == labelset_manifest_sha256
        for value in result["labelset_manifest_sha256"]
    ):
        raise CommitteeError(
            "pool labelset_manifest_sha256 does not match the requested frozen labelset."
        )
    _validate_finite_features(result, feature_order, "pool")
    return result


def _score_frame(
    frame: pd.DataFrame,
    *,
    logistic: LogisticQueryModel,
    boosted: HistGradientBoostingQueryModel,
    include_target: str | None,
    preserve_input_columns: bool,
) -> pd.DataFrame:
    logistic_scores = logistic.predict_probabilities(frame)
    boosted_scores = boosted.predict_probabilities(frame)
    result = (
        frame.copy()
        if preserve_input_columns
        else frame.loc[:, ["sample_id", "query_region_id", "dataset_role"]].copy()
    )
    if include_target is not None:
        result[include_target] = frame[include_target].astype(int).to_numpy()
        result["label_source_type"] = frame["label_source_type"].to_numpy()
        result["labelset_version"] = frame["labelset_version"].to_numpy()
    else:
        result["labelset_version"] = logistic.labelset_version
    result["feature_schema_version"] = logistic.feature_schema_version
    result["logistic_query_score"] = logistic_scores.to_numpy(dtype=float)
    result["boosted_query_score"] = boosted_scores.to_numpy(dtype=float)
    means = 0.5 * (
        result["logistic_query_score"] + result["boosted_query_score"]
    )
    result["committee_mean_query_score"] = means
    result["normalized_entropy"] = [
        normalized_binary_entropy(value) for value in means
    ]
    result["absolute_disagreement"] = [
        absolute_probability_disagreement(first, second)
        for first, second in zip(
            result["logistic_query_score"], result["boosted_query_score"]
        )
    ]
    result["jensen_shannon_disagreement"] = [
        jensen_shannon_disagreement(first, second)
        for first, second in zip(
            result["logistic_query_score"], result["boosted_query_score"]
        )
    ]
    for field, value in QUERY_MODEL_ELIGIBILITY.as_manifest_fields().items():
        result[field] = value
    return result


def _train_logistic(
    frame: pd.DataFrame,
    *,
    feature_order: tuple[str, ...],
    target_column: str,
    model_id: str,
    feature_schema_version: str,
    labelset_version: str,
    trained_at_utc: str,
    epochs: int,
    learning_rate: float,
    l2: float,
) -> LogisticQueryModel:
    try:
        return train_logistic_query_model(
            frame,
            feature_order=feature_order,
            label_column=target_column,
            model_id=model_id,
            feature_schema_version=feature_schema_version,
            labelset_version=labelset_version,
            epochs=epochs,
            learning_rate=learning_rate,
            l2=l2,
            trained_at_utc=trained_at_utc,
        )
    except QueryModelError as exc:
        raise CommitteeError(f"logistic query-model training failed: {exc}") from exc


def _train_boosted(
    frame: pd.DataFrame,
    *,
    feature_order: tuple[str, ...],
    target_column: str,
    model_id: str,
    feature_schema_version: str,
    labelset_version: str,
    trained_at_utc: str,
    random_seed: int,
    parameters: Mapping[str, object] | None,
) -> HistGradientBoostingQueryModel:
    supplied = dict(parameters or {})
    if supplied.get("early_stopping") not in (None, False):
        raise CommitteeError(
            "boosted query committee requires early_stopping=False; random "
            "internal validation splits are prohibited."
        )
    supplied["early_stopping"] = False
    try:
        model = train_hist_gradient_boosting_query_model(
            frame,
            feature_order=feature_order,
            label_column=target_column,
            model_id=model_id,
            feature_schema_version=feature_schema_version,
            labelset_version=labelset_version,
            random_state=random_seed,
            estimator_parameters=supplied,
            trained_at_utc=trained_at_utc,
        )
        parameters_used = model.to_manifest().get("estimator_parameters", {})
        if not isinstance(parameters_used, Mapping) or parameters_used.get(
            "early_stopping"
        ) is not False:
            raise CommitteeError(
                "boosted estimator did not retain early_stopping=False."
            )
        return model
    except QueryModelDependencyError as exc:
        raise CommitteeDependencyError(
            "query-committee training requires optional scikit-learn; install "
            "the FloodGuard `ml` extra (for example `pip install -e .[ml]`)."
        ) from exc
    except QueryModelError as exc:
        raise CommitteeError(f"boosted query-model training failed: {exc}") from exc


def _run_manifest(
    result: QueryCommitteeResult,
    *,
    artifact_paths: Sequence[tuple[str, Path]],
    training_source: str | Path | None,
    pool_source: str | Path | None,
    verified_training_derivation: VerifiedTrainingDerivation | None,
    provenance_sources: Mapping[str, str | Path] | None,
) -> dict[str, object]:
    artifacts = [
        {
            "name": name,
            "file": path.name,
            "sha256": _file_sha256(path),
            "bytes": path.stat().st_size,
        }
        for name, path in artifact_paths
    ]
    inputs: dict[str, object] = {
        "training_rows_sha256": result.training_rows_sha256,
        "pool_rows_sha256": result.pool_rows_sha256,
    }
    if training_source is not None:
        source = _existing_file(training_source, "training source")
        inputs["training_source"] = {
            "file": source.name,
            "sha256": _file_sha256(source),
        }
    if pool_source is not None:
        source = _existing_file(pool_source, "pool source")
        inputs["pool_source"] = {
            "file": source.name,
            "sha256": _file_sha256(source),
        }
    if verified_training_derivation is not None:
        inputs["verified_training_derivation"] = {
            "labelset_id": verified_training_derivation.labelset_id,
            "labelset_manifest_sha256": (
                verified_training_derivation.labelset_manifest_sha256
            ),
            "release_validation_receipt_sha256": (
                verified_training_derivation.release_validation_receipt_sha256
            ),
            "training_csv_sha256": verified_training_derivation.training_csv_sha256,
            "derivation_manifest_sha256": (
                verified_training_derivation.derivation_manifest_sha256
            ),
            "grid_contract_sha256": (
                verified_training_derivation.grid_contract_sha256
            ),
            "query_region_ids": list(verified_training_derivation.query_region_ids),
            "row_count": verified_training_derivation.row_count,
        }
    if provenance_sources:
        inputs["provenance_sources"] = {
            name: {
                "file": _existing_file(path, name).name,
                "sha256": _file_sha256(_existing_file(path, name)),
            }
            for name, path in sorted(provenance_sources.items())
        }
    fold_rows = [
        {
            "repeat_index": fold.repeat_index,
            "fold_index": fold.fold_index,
            "validation_groups": list(fold.validation_groups),
            "training_rows": fold.training_rows,
            "validation_rows": fold.validation_rows,
        }
        for fold in result.folds
    ]
    return {
        "artifact_schema": COMMITTEE_RUN_SCHEMA,
        "run_id": result.run_id,
        "trained_at_utc": result.trained_at_utc,
        "feature_contract": {
            "feature_schema_version": result.feature_schema_version,
            "feature_schema_sha256": result.feature_schema_sha256,
            "feature_order": list(result.feature_order),
        },
        "label_contract": {
            "labelset_version": result.labelset_version,
            "labelset_manifest_sha256": result.labelset_manifest_sha256,
            "target_column": result.target_column,
            "accepted_label_source_types": sorted(ALLOWED_LABEL_SOURCE_TYPES),
            "excluded_label_classes": [
                "uncertain_water_change",
                "unobservable",
                "unreviewed",
            ],
        },
        "cross_validation": {
            "kind": "repeated_deterministic_spatial_group",
            "group_column": result.group_column,
            "n_splits": result.n_splits,
            "n_repeats": result.n_repeats,
            "random_seed": result.random_seed,
            "folds": fold_rows,
        },
        "models": {
            "logistic_model_id": result.logistic_model.model_id,
            "boosted_model_id": result.boosted_model.model_id,
            "boosted_persistence": "non_executable_manifest_only",
            "score_semantics": "continuous query-ranking scores only",
        },
        "row_counts": {
            "reviewed_training_rows": result.logistic_model.training_rows,
            "grouped_oof_score_rows": len(result.oof_scores),
            "query_pool_score_rows": len(result.pool_scores),
        },
        "inputs": inputs,
        "artifacts": artifacts,
        "safety": {
            **QUERY_MODEL_ELIGIBILITY.as_manifest_fields(),
            "creates_flood_truth": False,
            "classification_cutoff_selected": False,
            "allowed_output_use": "blinded_human_review_queue_prioritisation",
        },
        "warning": QUERY_COMMITTEE_WARNING,
    }


def _validate_result_for_persistence(result: QueryCommitteeResult) -> None:
    """Recheck mutable DataFrames and model flags before artifact creation."""

    model_safety = {
        "query_model_only": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }
    for model_name, model in (
        ("logistic", result.logistic_model),
        ("boosted", result.boosted_model),
    ):
        for field, expected in model_safety.items():
            if getattr(model, field, None) is not expected:
                raise CommitteeError(
                    f"{model_name} model safety field {field} must remain {expected}."
                )
    if result.logistic_model.labelset_version != result.labelset_version:
        raise CommitteeError("logistic model labelset differs from the committee run.")
    if result.boosted_model.labelset_version != result.labelset_version:
        raise CommitteeError("boosted model labelset differs from the committee run.")
    if result.logistic_model.feature_order != result.feature_order:
        raise CommitteeError("logistic model feature order differs from the run.")
    if result.boosted_model.feature_order != result.feature_order:
        raise CommitteeError("boosted model feature order differs from the run.")
    for label, frame in (
        ("OOF", result.oof_scores),
        ("pool", result.pool_scores),
    ):
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            raise CommitteeError(f"{label} score output must be a non-empty DataFrame.")
        forbidden_columns = [
            column
            for column in frame.columns
            if "threshold" in str(column).lower()
            or str(column).lower() in {"cutoff", "decision_boundary"}
        ]
        if forbidden_columns:
            raise CommitteeError(
                f"{label} score output contains prohibited cutoff fields: "
                f"{forbidden_columns!r}."
            )
        for field, expected in QUERY_MODEL_ELIGIBILITY.as_manifest_fields().items():
            if field not in frame:
                raise CommitteeError(
                    f"{label} score output is missing safety field {field}."
                )
            values = frame[field]
            if isinstance(expected, bool):
                if not all(
                    _is_literal_bool(value, expected=expected) for value in values
                ):
                    raise CommitteeError(
                        f"{label} score safety field {field} must remain {expected}."
                    )
            elif not all(
                isinstance(value, str) and value == expected for value in values
            ):
                raise CommitteeError(
                    f"{label} score safety field {field} must remain {expected!r}."
                )
        for score_column in ("logistic_query_score", "boosted_query_score"):
            if score_column not in frame:
                raise CommitteeError(f"{label} output is missing {score_column}.")
            scores = pd.to_numeric(frame[score_column], errors="coerce")
            if scores.isna().any() or not scores.between(0.0, 1.0).all():
                raise CommitteeError(
                    f"{label} {score_column} values must be finite scores in [0, 1]."
                )


def _resolve_feature_order(
    feature_schema_version: str,
    feature_order: Sequence[str] | None,
) -> tuple[str, ...]:
    try:
        schema = get_feature_schema(feature_schema_version)
        if schema.version != "sar_change_v2" or schema.legacy:
            raise CommitteeError(
                "The query committee accepts only the canonical non-legacy "
                "sar_change_v2 feature schema."
            )
        requested = (
            schema.required_feature_names
            if feature_order is None
            else tuple(feature_order)
        )
        if not requested or isinstance(feature_order, (str, bytes)):
            raise CommitteeError("feature_order must be a sequence of column names.")
        ordered = schema.validate_columns(requested, allow_extra=False)
    except FeatureSchemaError as exc:
        raise CommitteeError(str(exc)) from exc
    if tuple(requested) != ordered:
        raise CommitteeError(
            f"feature_order must follow schema {feature_schema_version!r}: "
            f"{', '.join(ordered)}."
        )
    return ordered


def _validate_finite_features(
    frame: pd.DataFrame,
    feature_order: Sequence[str],
    label: str,
) -> None:
    import numpy as np

    numeric = frame.loc[:, list(feature_order)].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
        raise CommitteeError(f"{label} features must be finite numeric values.")


def _validated_binary_target(series: pd.Series, label: str) -> list[int]:
    import numpy as np

    values: list[int] = []
    for index, value in series.items():
        if isinstance(value, (bool, np.bool_)):
            raise CommitteeError(
                f"{label} row {index} must be explicit integer 0/1, not boolean."
            )
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise CommitteeError(f"{label} row {index} is not explicit 0/1.") from exc
        if not math.isfinite(numeric) or numeric not in (0.0, 1.0):
            raise CommitteeError(f"{label} row {index} is not explicit 0/1.")
        values.append(int(numeric))
    return values


def _validated_identifier_series(
    series: pd.Series,
    label: str,
    *,
    unique: bool,
) -> list[str]:
    values = [_stable_identifier(value, label) for value in series]
    if unique and len(values) != len(set(values)):
        duplicates = sorted(pd.Series(values)[pd.Series(values).duplicated()].unique())
        raise CommitteeError(f"{label} values must be unique; duplicates: {duplicates!r}.")
    return values


def _stable_identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER_PATTERN.fullmatch(value):
        raise CommitteeError(
            f"{label} must be a stable non-blank identifier using letters, "
            "numbers, dot, underscore, colon, or hyphen."
        )
    return value


def _require_single_group_per_query(frame: pd.DataFrame, group_column: str) -> None:
    counts = frame.groupby("query_region_id", sort=False)[group_column].nunique()
    bad = sorted(counts[counts > 1].index.astype(str).tolist())
    if bad:
        raise CommitteeError(
            "each query_region_id must map to exactly one spatial group; "
            f"violations: {bad[:5]!r}."
        )


def _role_value(value: object) -> str:
    if isinstance(value, DatasetRole):
        return value.value
    if not isinstance(value, str):
        raise CommitteeError(f"dataset_role must be an exact string; got {value!r}.")
    try:
        return DatasetRole(value).value
    except ValueError as exc:
        raise CommitteeError(f"unknown dataset_role {value!r}.") from exc


def _is_literal_bool(value: object, *, expected: bool) -> bool:
    import numpy as np

    return isinstance(value, (bool, np.bool_)) and bool(value) is expected


def _require_columns(
    frame: pd.DataFrame,
    required: Sequence[str],
    label: str,
) -> None:
    missing = [name for name in dict.fromkeys(required) if name not in frame]
    if missing:
        raise CommitteeError(
            f"{label} input is missing required columns: {', '.join(missing)}."
        )


def _feature_schema_sha256(version: str) -> str:
    schema = get_feature_schema(version)
    payload = {
        "version": schema.version,
        "legacy": schema.legacy,
        "intended_use": schema.intended_use,
        "source_contract": schema.source_contract,
        "features": [asdict(feature) for feature in schema.features],
    }
    return hashlib.sha256(_json_text(payload).encode("utf-8")).hexdigest()


def _sha256_text(value: object, label: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-fA-F]{64}", value) is None:
        raise CommitteeError(f"{label} must contain exactly 64 hexadecimal digits.")
    return value.lower()


def _frame_sha256(frame: pd.DataFrame) -> str:
    payload = frame.to_csv(index=False, lineterminator="\n", float_format="%.17g")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_hash_key(random_seed: int, repeat_zero: int, group: str) -> str:
    return hashlib.sha256(
        f"{random_seed}:{repeat_zero}:{group}".encode("utf-8")
    ).hexdigest()


def _assert_no_cutoff_fields(value: object) -> None:
    """Reject persisted classification-cutoff fields from query-only artifacts."""

    if isinstance(value, Mapping):
        for key, nested in value.items():
            lowered = str(key).lower()
            if "threshold" in lowered or lowered in {"cutoff", "decision_boundary"}:
                raise CommitteeError(
                    f"query-committee artifact may not persist model cutoff field {key!r}."
                )
            _assert_no_cutoff_fields(nested)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for nested in value:
            _assert_no_cutoff_fields(nested)


def _json_text(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def _existing_csv(value: str | Path, label: str) -> Path:
    path = _existing_file(value, label)
    if path.suffix.lower() != ".csv":
        raise CommitteeError(f"{label} input must be a CSV file: {path}")
    return path


def _existing_file(value: str | Path, label: str) -> Path:
    path = Path(value)
    if not path.is_file():
        raise CommitteeError(f"{label} file does not exist: {path}")
    return path


def _require_new_output_directory(path: Path) -> None:
    if path.exists():
        raise CommitteeError(
            f"output directory already exists and will not be overwritten: {path}"
        )


def _validated_timestamp(value: str | None) -> str:
    if value is None:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")
    text = _non_blank(value, "trained_at_utc")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CommitteeError("trained_at_utc must be an ISO-8601 timestamp.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CommitteeError("trained_at_utc must include an explicit timezone.")
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _non_blank(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CommitteeError(f"{label} must be a non-blank string.")
    return value.strip()


def _positive_int(value: object, label: str, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise CommitteeError(f"{label} must be an integer >= {minimum}.")
    return value
