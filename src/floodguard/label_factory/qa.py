"""Fail-closed quality checks for label-factory evidence and model isolation.

The QA layer accepts plain mappings or small record objects so it can validate
CSV-derived rows without introducing a dataframe dependency.  Every hard gate
produces a structured finding; callers must explicitly inspect ``report.ready``
or call ``report.raise_for_failures()`` before freezing a labelset.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from floodguard.label_factory.annotations import (
    BINARY_TARGET_BY_CLASS,
    AnnotationRecord,
    LabelClass,
    coerce_label_class,
)
from floodguard.label_factory.contracts import (
    DatasetRole,
    HumanReviewedTrainingEligibility,
    ModelPurpose,
)


QA_VALIDATOR_VERSION = "label_factory_qa_v1"


class LabelFactoryQAError(ValueError):
    """Raised when a caller attempts to use evidence that failed hard QA."""


class QASeverity(str, Enum):
    """Finding severity and freeze-blocking policy."""

    CRITICAL = "critical"
    HIGH = "high"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class QAFinding:
    """One auditable quality check result."""

    check_id: str
    entity_id: str
    passed: bool
    severity: QASeverity
    message: str
    observed: str
    expected: str

    @property
    def blocking(self) -> bool:
        """Return whether this failed finding prevents labelset freeze."""

        return not self.passed and self.severity in {
            QASeverity.CRITICAL,
            QASeverity.HIGH,
        }


@dataclass(frozen=True, slots=True)
class QAReport:
    """Collection of QA findings with a fail-closed readiness decision."""

    findings: tuple[QAFinding, ...]

    @property
    def failures(self) -> tuple[QAFinding, ...]:
        """Return all failed checks."""

        return tuple(finding for finding in self.findings if not finding.passed)

    @property
    def blocking_failures(self) -> tuple[QAFinding, ...]:
        """Return failures that block labelset freeze."""

        return tuple(finding for finding in self.findings if finding.blocking)

    @property
    def ready(self) -> bool:
        """Return ``True`` only when no blocking findings remain."""

        return not self.blocking_failures

    def raise_for_failures(self) -> None:
        """Raise a compact error containing every blocking check."""

        if self.ready:
            return
        details = "; ".join(
            f"{finding.check_id}[{finding.entity_id}]: {finding.message}"
            for finding in self.blocking_failures
        )
        raise LabelFactoryQAError(f"Label-factory QA failed: {details}")

    def to_rows(self) -> list[dict[str, Any]]:
        """Return CSV/dataframe-friendly finding rows."""

        return [
            {
                "check_id": finding.check_id,
                "entity_id": finding.entity_id,
                "passed": finding.passed,
                "severity": finding.severity.value,
                "message": finding.message,
                "observed": finding.observed,
                "expected": finding.expected,
            }
            for finding in self.findings
        ]


DATASET_ROLES: frozenset[str] = frozenset(role.value for role in DatasetRole)

FORBIDDEN_TEST_PURPOSES: frozenset[str] = frozenset(
    {
        "acquisition",
        "active_learning_selection",
        "training",
        "calibration",
        "threshold_selection",
        "model_selection",
        "feature_selection",
        "hyperparameter_tuning",
    }
)

ALLOWED_UNTOUCHED_TEST_PURPOSES: frozenset[str] = frozenset(
    {
        "final_evaluation",
        "untouched_geographic_evaluation",
        "report_only_audit",
    }
)


def run_label_factory_qa(
    *,
    source_assets: Sequence[Any] | None = None,
    dataset_assignments: Sequence[Any] | None = None,
    usage_records: Sequence[Any] | None = None,
    query_models: Sequence[Any] | None = None,
    query_records: Sequence[Any] | None = None,
    annotations: Sequence[Any] | None = None,
    binary_training_rows: Sequence[Any] | None = None,
    require_complete_annotations: bool = True,
) -> QAReport:
    """Run all supplied label-factory QA lanes and return one report.

    ``None`` means a lane was outside the caller's current scope.  Supplying an
    empty collection means the lane was expected but has no evidence and is a
    failure for checks that require at least one row.
    """

    findings: list[QAFinding] = []
    if source_assets is not None:
        findings.extend(validate_source_assets(source_assets))
    if dataset_assignments is not None:
        findings.extend(validate_dataset_roles(dataset_assignments))
    if usage_records is not None:
        findings.extend(
            validate_test_set_isolation(dataset_assignments or (), usage_records)
        )
    if query_models is not None:
        findings.extend(validate_query_model_safety(query_models))
    if query_records is not None:
        findings.extend(validate_random_control_lane(query_records))
    if annotations is not None:
        findings.extend(
            validate_annotation_records(
                annotations,
                require_complete=require_complete_annotations,
            )
        )
    if binary_training_rows is not None:
        findings.extend(validate_binary_training_rows(binary_training_rows))
    return QAReport(findings=tuple(findings))


def validate_source_assets(source_assets: Sequence[Any]) -> list[QAFinding]:
    """Validate product IDs, timestamps, rights, and pre/post temporal order."""

    if not source_assets:
        return [
            _finding(
                "source_assets_present",
                "source_assets",
                False,
                "No source assets were supplied.",
                observed="0 rows",
                expected="at least one explicit source asset",
            )
        ]

    findings: list[QAFinding] = []
    event_roles: dict[str, dict[str, list[tuple[str, datetime]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for index, asset in enumerate(source_assets):
        entity_id = _entity_id(asset, f"source_asset[{index}]")
        product_id = _row_value(asset, "product_id")
        product_ok = _is_nonblank(product_id)
        findings.append(
            _finding(
                "source_product_id",
                entity_id,
                product_ok,
                "Source product ID is present." if product_ok else "Source product ID is missing.",
                observed=str(product_id),
                expected="non-blank product_id",
            )
        )

        acquisition_raw = _first_row_value(
            asset, "acquisition_time", "acquisition_time_utc"
        )
        acquisition = _parse_aware_timestamp(acquisition_raw)
        timestamp_ok = acquisition is not None
        findings.append(
            _finding(
                "source_acquisition_time",
                entity_id,
                timestamp_ok,
                (
                    "Source acquisition timestamp is timezone-aware."
                    if timestamp_ok
                    else "Source acquisition timestamp is missing, invalid, or lacks timezone."
                ),
                observed=str(acquisition_raw),
                expected="timezone-aware ISO-8601 acquisition_time",
            )
        )

        for required_use in ("processing", "label_derivation"):
            permission = _explicit_use_permission(asset, required_use)
            findings.append(
                _finding(
                    f"rights_{required_use}",
                    entity_id,
                    permission is True,
                    (
                        f"{required_use} use is explicitly permitted."
                        if permission is True
                        else f"{required_use} use is not explicitly permitted."
                    ),
                    observed=str(permission),
                    expected="explicit true permission",
                )
            )

        event_id = _row_value(asset, "event_id")
        asset_role = _normalized_source_role(
            _first_row_value(asset, "asset_role", "event_relative_role")
        )
        if _is_nonblank(event_id) and asset_role in {"pre_event", "post_event"}:
            if acquisition is not None:
                event_roles[str(event_id).strip()][asset_role].append(
                    (entity_id, acquisition)
                )

    declared_pair_events = {
        str(_row_value(asset, "event_id")).strip()
        for asset in source_assets
        if _normalized_source_role(
            _first_row_value(asset, "asset_role", "event_relative_role")
        )
        in {"pre_event", "post_event"}
        and _is_nonblank(_row_value(asset, "event_id"))
    }
    for event_id in sorted(declared_pair_events):
        roles = event_roles[event_id]
        pre_rows = roles.get("pre_event", [])
        post_rows = roles.get("post_event", [])
        complete = bool(pre_rows and post_rows)
        findings.append(
            _finding(
                "pre_post_pair_present",
                event_id,
                complete,
                (
                    "Event contains timestamped pre- and post-event assets."
                    if complete
                    else "Event is missing a valid pre- or post-event asset."
                ),
                observed=f"pre={len(pre_rows)}, post={len(post_rows)}",
                expected="at least one valid pre_event and post_event asset",
            )
        )
        if complete:
            latest_pre = max(timestamp for _, timestamp in pre_rows)
            earliest_post = min(timestamp for _, timestamp in post_rows)
            ordered = latest_pre < earliest_post
            findings.append(
                _finding(
                    "pre_before_post",
                    event_id,
                    ordered,
                    (
                        "All selected pre-event evidence precedes post-event evidence."
                        if ordered
                        else "Pre-event acquisition does not precede post-event acquisition."
                    ),
                    observed=f"latest_pre={latest_pre.isoformat()}, earliest_post={earliest_post.isoformat()}",
                    expected="latest_pre < earliest_post",
                )
            )
    return findings


def validate_dataset_roles(assignments: Sequence[Any]) -> list[QAFinding]:
    """Reject entity or spatial-overlap groups assigned to multiple roles."""

    if not assignments:
        return [
            _finding(
                "dataset_assignments_present",
                "dataset_assignments",
                False,
                "No dataset-role assignments were supplied.",
                observed="0 rows",
                expected="at least one assignment",
            )
        ]

    findings: list[QAFinding] = []
    entity_roles: dict[str, set[str]] = defaultdict(set)
    overlap_roles: dict[str, set[str]] = defaultdict(set)
    for index, assignment in enumerate(assignments):
        entity_id = _entity_id(assignment, f"assignment[{index}]")
        role = _normalized_text(_row_value(assignment, "dataset_role"))
        role_ok = role in DATASET_ROLES
        findings.append(
            _finding(
                "dataset_role_known",
                entity_id,
                role_ok,
                "Dataset role is recognized." if role_ok else "Dataset role is missing or unknown.",
                observed=role,
                expected=", ".join(sorted(DATASET_ROLES)),
            )
        )
        if not role_ok:
            continue
        entity_roles[entity_id].add(role)
        overlap_group = _first_row_value(
            assignment, "overlap_group", "overlap_group_id"
        )
        if _is_nonblank(overlap_group):
            overlap_roles[str(overlap_group).strip()].add(role)

    for entity_id, roles in sorted(entity_roles.items()):
        findings.append(
            _finding(
                "entity_single_dataset_role",
                entity_id,
                len(roles) == 1,
                (
                    "Entity belongs to exactly one dataset role."
                    if len(roles) == 1
                    else "Entity appears in multiple dataset roles."
                ),
                observed=", ".join(sorted(roles)),
                expected="exactly one role",
            )
        )
    for overlap_group, roles in sorted(overlap_roles.items()):
        findings.append(
            _finding(
                "overlap_group_single_dataset_role",
                overlap_group,
                len(roles) == 1,
                (
                    "Spatial overlap group belongs to exactly one dataset role."
                    if len(roles) == 1
                    else "Spatial overlap group leaks across dataset roles."
                ),
                observed=", ".join(sorted(roles)),
                expected="exactly one role",
            )
        )
    return findings


def validate_test_set_isolation(
    assignments: Sequence[Any],
    usage_records: Sequence[Any],
) -> list[QAFinding]:
    """Reject acquisition, fitting, calibration, or tuning use of test regions."""

    role_by_entity: dict[str, str] = {}
    for assignment in assignments:
        entity_id = _entity_id(assignment, "unknown_assignment")
        role = _normalized_text(_row_value(assignment, "dataset_role"))
        if entity_id in role_by_entity and role_by_entity[entity_id] != role:
            role_by_entity[entity_id] = "__role_conflict__"
        else:
            role_by_entity[entity_id] = role

    if not usage_records:
        return [
            _finding(
                "usage_records_present",
                "usage_records",
                False,
                "No usage records were supplied for test-isolation audit.",
                observed="0 rows",
                expected="explicit usage lineage",
            )
        ]

    findings: list[QAFinding] = []
    for index, usage in enumerate(usage_records):
        subject_id = _entity_id(usage, f"usage[{index}]")
        purpose = _normalized_text(_row_value(usage, "purpose"))
        explicit_usage_id = _first_row_value(
            usage, "usage_record_id", "usage_id"
        )
        entity_id = (
            str(explicit_usage_id).strip()
            if _is_nonblank(explicit_usage_id)
            else f"{subject_id}::{purpose or 'missing-purpose'}::{index + 1}"
        )
        role = role_by_entity.get(subject_id)
        known = role in DATASET_ROLES
        findings.append(
            _finding(
                "usage_has_dataset_role",
                entity_id,
                known,
                (
                    "Usage record resolves to a frozen dataset role."
                    if known
                    else "Usage record has no unique, recognized dataset role."
                ),
                observed=f"subject={subject_id}, role={role}",
                expected="recognized dataset role",
            )
        )
        if not known:
            continue
        isolated = (
            role != "untouched_geographic_test"
            or purpose in ALLOWED_UNTOUCHED_TEST_PURPOSES
        )
        findings.append(
            _finding(
                "untouched_test_isolation",
                entity_id,
                isolated,
                (
                    "Usage preserves untouched geographic-test isolation."
                    if isolated
                    else "Untouched geographic-test evidence was used before final evaluation."
                ),
                observed=f"role={role}, purpose={purpose}",
                expected="test evidence used only for final evaluation/reporting",
            )
        )
    return findings


def validate_query_model_safety(query_models: Sequence[Any]) -> list[QAFinding]:
    """Enforce the permanent report-only boundary for acquisition models."""

    if not query_models:
        return [
            _finding(
                "query_models_present",
                "query_models",
                False,
                "No query-model safety records were supplied.",
                observed="0 rows",
                expected="at least one model manifest",
            )
        ]

    findings: list[QAFinding] = []
    for index, model in enumerate(query_models):
        entity_id = _entity_id(model, f"query_model[{index}]")
        required_true = {
            "query_model_only": True,
            "eligible_for_review_queue": True,
        }
        required_false = {
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
        }
        for field_name, expected in {**required_true, **required_false}.items():
            observed = _row_value(model, field_name)
            passed = observed is expected
            findings.append(
                _finding(
                    f"query_model_{field_name}",
                    entity_id,
                    passed,
                    (
                        f"Query-model {field_name} is safely fixed to {expected}."
                        if passed
                        else f"Query-model {field_name} violates the safety contract."
                    ),
                    observed=repr(observed),
                    expected=repr(expected),
                )
            )
        expected_scalars = {
            "model_purpose": ModelPurpose.QUERY_RANKING.value,
            "eligible_for_training_after_human_review": (
                HumanReviewedTrainingEligibility.CONDITIONAL.value
            ),
        }
        for field_name, expected in expected_scalars.items():
            observed = _row_value(model, field_name)
            passed = observed == expected
            findings.append(
                _finding(
                    f"query_model_{field_name}",
                    entity_id,
                    passed,
                    (
                        f"Query-model {field_name} matches the canonical contract."
                        if passed
                        else f"Query-model {field_name} violates the canonical contract."
                    ),
                    observed=repr(observed),
                    expected=repr(expected),
                )
            )
    return findings


def validate_random_control_lane(query_records: Sequence[Any]) -> list[QAFinding]:
    """Require at least one selected random-control query in every round."""

    if not query_records:
        return [
            _finding(
                "query_records_present",
                "query_records",
                False,
                "No query-selection records were supplied.",
                observed="0 rows",
                expected="at least one selected query",
            )
        ]

    selected_by_round: dict[str, list[Any]] = defaultdict(list)
    for index, record in enumerate(query_records):
        selected = _row_value(record, "selected")
        if selected is True:
            round_id = _row_value(record, "round_id")
            round_key = str(round_id).strip() if _is_nonblank(round_id) else ""
            selected_by_round[round_key].append(record)

    if not selected_by_round:
        return [
            _finding(
                "selected_queries_present",
                "query_records",
                False,
                "No explicitly selected query rows were found.",
                observed="0 selected rows",
                expected="selected is literal true",
            )
        ]

    findings: list[QAFinding] = []
    for round_id, records in sorted(selected_by_round.items()):
        valid_round_id = bool(round_id)
        findings.append(
            _finding(
                "query_round_id_present",
                round_id or "missing_round_id",
                valid_round_id,
                "Selected queries identify their round." if valid_round_id else "Selected query round_id is missing.",
                observed=round_id or "blank",
                expected="non-blank round_id",
            )
        )
        random_count = sum(
            _normalized_text(_row_value(record, "selection_lane")) == "random_control"
            for record in records
        )
        findings.append(
            _finding(
                "random_control_lane_present",
                round_id or "missing_round_id",
                random_count > 0,
                (
                    "Round contains a selected random-control query."
                    if random_count > 0
                    else "Round has no selected random-control query."
                ),
                observed=f"{random_count} random-control rows",
                expected="at least 1 selected random_control row",
            )
        )
        random_records = [
            record
            for record in records
            if _normalized_text(_row_value(record, "selection_lane"))
            == "random_control"
        ]
        sampling_design_valid = bool(random_records) and all(
            _valid_random_sampling_record(record) for record in random_records
        )
        findings.append(
            _finding(
                "random_control_sampling_design",
                round_id or "missing_round_id",
                sampling_design_valid,
                (
                    "Random-control rows retain their stratified sampling frame, "
                    "quota, and inclusion probability."
                    if sampling_design_valid
                    else "Random-control rows lack a valid auditable inclusion probability."
                ),
                observed=f"{len(random_records)} random-control rows",
                expected=(
                    "nonblank sampling_stratum, positive population/quota, and "
                    "inclusion_probability == quota / population in (0, 1]"
                ),
                severity=QASeverity.HIGH,
            )
        )
    return findings


def _valid_random_sampling_record(record: Any) -> bool:
    """Return whether a selected random-control row has a coherent design receipt."""

    if not _is_nonblank(_row_value(record, "sampling_stratum")):
        return False
    try:
        population_number = float(
            _row_value(record, "sampling_stratum_population")
        )
        quota_number = float(_row_value(record, "sampling_stratum_quota"))
        probability = float(_row_value(record, "inclusion_probability"))
    except (TypeError, ValueError):
        return False
    population = int(population_number)
    quota = int(quota_number)
    if (
        population_number != population
        or quota_number != quota
        or population <= 0
        or quota <= 0
        or quota > population
        or not 0.0 < probability <= 1.0
    ):
        return False
    return abs(probability - (quota / population)) <= 1e-12


def validate_annotation_records(
    annotations: Sequence[Any],
    *,
    require_complete: bool = True,
) -> list[QAFinding]:
    """Validate reviewer identity, explicit coverage, locking, and blinding."""

    if not annotations:
        return [
            _finding(
                "annotations_present",
                "annotations",
                False,
                "No reviewer annotations were supplied.",
                observed="0 rows",
                expected="at least one reviewer annotation",
            )
        ]

    findings: list[QAFinding] = []
    for index, annotation in enumerate(annotations):
        entity_id = _entity_id(annotation, f"annotation[{index}]")
        checks = [
            (
                "annotation_reviewer_id",
                _is_nonblank(_row_value(annotation, "reviewer_id")),
                "non-blank reviewer_id",
            ),
            (
                "annotation_reviewed_extent",
                _is_nonblank(_row_value(annotation, "reviewed_extent")),
                "explicit non-blank reviewed_extent",
            ),
            (
                "annotation_model_blinding",
                _row_value(annotation, "model_predictions_visible") is False,
                "model_predictions_visible is literal false",
            ),
            (
                "annotation_reviewer_blinding",
                _row_value(
                    annotation,
                    "other_reviewer_annotations_visible",
                    False if isinstance(annotation, AnnotationRecord) else None,
                )
                is False,
                "other_reviewer_annotations_visible is literal false",
            ),
        ]
        if require_complete:
            checks.extend(
                [
                    (
                        "annotation_review_complete",
                        _row_value(annotation, "review_complete") is True,
                        "review_complete is literal true",
                    ),
                    (
                        "annotation_locked",
                        _row_value(annotation, "locked_at_utc") is not None,
                        "locked_at_utc is present",
                    ),
                ]
            )
        for check_id, passed, expected in checks:
            findings.append(
                _finding(
                    check_id,
                    entity_id,
                    passed,
                    (
                        "Annotation satisfies the review contract."
                        if passed
                        else "Annotation violates the review contract."
                    ),
                    observed=repr(_observed_for_annotation_check(annotation, check_id)),
                    expected=expected,
                )
            )
    return findings


def validate_binary_training_rows(rows: Sequence[Any]) -> list[QAFinding]:
    """Reject uncertain, unobservable, unreviewed, or mis-mapped training rows."""

    if not rows:
        return [
            _finding(
                "binary_training_rows_present",
                "binary_training_rows",
                False,
                "No binary training rows were supplied; the release contains no "
                "eligible binary candidates.",
                observed="0 rows",
                expected="zero or more explicitly reviewed training rows",
                severity=QASeverity.WARNING,
            ),
            _finding(
                "binary_training_label_known",
                "binary_training_rows",
                True,
                "The empty candidate set contains no unknown label codes.",
                observed="0 rows",
                expected="all supplied label codes are canonical",
            ),
            _finding(
                "binary_training_label_eligible",
                "binary_training_rows",
                True,
                "The empty candidate set contains no ineligible labels.",
                observed="0 rows",
                expected="all supplied label codes are in {0, 1, 2}",
            ),
            _finding(
                "binary_training_target_mapping",
                "binary_training_rows",
                True,
                "The empty candidate set contains no incorrect binary targets.",
                observed="0 rows",
                expected="all supplied targets follow the fixed class mapping",
            ),
        ]

    findings: list[QAFinding] = []
    for index, row in enumerate(rows):
        entity_id = _entity_id(row, f"binary_row[{index}]")
        raw_label = _row_value(row, "label_code")
        try:
            label = coerce_label_class(raw_label)
        except ValueError:
            findings.append(
                _finding(
                    "binary_training_label_known",
                    entity_id,
                    False,
                    "Binary training row has an unknown label code.",
                    observed=repr(raw_label),
                    expected="canonical label code",
                )
            )
            continue
        findings.append(
            _finding(
                "binary_training_label_known",
                entity_id,
                True,
                "Binary training row uses a canonical label code.",
                observed=repr(raw_label),
                expected="canonical label code",
            )
        )
        expected_target = BINARY_TARGET_BY_CLASS.get(label)
        eligible = expected_target is not None
        findings.append(
            _finding(
                "binary_training_label_eligible",
                entity_id,
                eligible,
                (
                    "Training row uses an explicitly resolved class."
                    if eligible
                    else "Uncertain, unobservable, or unreviewed class entered training."
                ),
                observed=f"label_code={int(label)}",
                expected="label_code in {0, 1, 2}",
            )
        )
        if eligible:
            observed_target = _row_value(row, "binary_target")
            correct_target = (
                type(observed_target) is int
                and observed_target == expected_target
            )
            findings.append(
                _finding(
                    "binary_training_target_mapping",
                    entity_id,
                    correct_target,
                    (
                        "Binary target matches the canonical class mapping."
                        if correct_target
                        else "Binary target does not match the canonical class mapping."
                    ),
                    observed=repr(observed_target),
                    expected=str(expected_target),
                )
            )
    return findings


def _observed_for_annotation_check(annotation: Any, check_id: str) -> Any:
    mapping = {
        "annotation_reviewer_id": "reviewer_id",
        "annotation_reviewed_extent": "reviewed_extent",
        "annotation_model_blinding": "model_predictions_visible",
        "annotation_reviewer_blinding": "other_reviewer_annotations_visible",
        "annotation_review_complete": "review_complete",
        "annotation_locked": "locked_at_utc",
    }
    return _row_value(annotation, mapping[check_id])


def _explicit_use_permission(row: Any, use_name: str) -> bool | None:
    boolean_field = f"{use_name}_allowed"
    explicit = _row_value(row, boolean_field)
    if explicit is None and use_name == "label_derivation":
        explicit = _row_value(row, "ml_label_derivation_allowed")
    if explicit is True:
        return True
    if explicit is False:
        return False

    allowed_uses = _row_value(row, "allowed_uses")
    if isinstance(allowed_uses, str):
        uses = {
            value.strip().lower()
            for value in allowed_uses.replace(";", ",").split(",")
            if value.strip()
        }
        return use_name in uses
    if isinstance(allowed_uses, Iterable) and not isinstance(
        allowed_uses,
        (str, bytes, Mapping),
    ):
        uses = {_normalized_text(value) for value in allowed_uses}
        return use_name in uses
    return None


def _parse_aware_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _row_value(row: Any, field_name: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(field_name, default)
    return getattr(row, field_name, default)


def _first_row_value(row: Any, *field_names: str) -> Any:
    for field_name in field_names:
        value = _row_value(row, field_name)
        if value is not None:
            return value
    return None


def _normalized_source_role(value: Any) -> str:
    role = _normalized_text(value)
    return "post_event" if role == "event_time" else role


def _entity_id(row: Any, fallback: str) -> str:
    for field_name in (
        "annotation_id",
        "sample_id",
        "model_id",
        "usage_record_id",
        "usage_id",
        "region_id",
        "cell_id",
        "query_region_id",
        "entity_id",
        "asset_id",
        "product_id",
    ):
        value = _row_value(row, field_name)
        if _is_nonblank(value):
            return str(value).strip()
    return fallback


def _is_nonblank(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _normalized_text(value: Any) -> str:
    return str(value).strip().lower() if value is not None else ""


def _finding(
    check_id: str,
    entity_id: str,
    passed: bool,
    message: str,
    *,
    observed: str,
    expected: str,
    severity: QASeverity = QASeverity.CRITICAL,
) -> QAFinding:
    return QAFinding(
        check_id=check_id,
        entity_id=entity_id,
        passed=passed,
        severity=severity,
        message=message,
        observed=observed,
        expected=expected,
    )
