"""Content-addressed release-QA assembly from exact raw evidence files.

This module closes an important trust boundary in the label factory.  A QA CSV
is not accepted merely because its findings say ``passed=true``.  The release
receipt records every raw input by role and SHA-256, and verification reloads
those exact bytes and reruns :func:`run_label_factory_qa` before a labelset can
be frozen or revalidated.

The module deliberately does not import ``review_workflow``.  The workflow can
therefore call :func:`verify_release_qa_artifacts` without creating a circular
dependency, while the assembler CLI may augment the workflow's existing
reviewer/agreement/raster bindings with the raw-input provenance defined here.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from floodguard.label_factory.annotations import (
    AnnotationRecord,
    AnnotationValidationError,
    annotation_content_sha256,
    load_annotation_log,
)
from floodguard.label_factory.qa import (
    QAReport,
    QA_VALIDATOR_VERSION,
    run_label_factory_qa,
)
from floodguard.label_factory.versioning import LabelsetVersionError, file_sha256


RELEASE_QA_RECEIPT_SCHEMA = "floodguard.label_factory_qa_receipt.v1"
RELEASE_QA_REPORT_SCHEMA = "floodguard.label_factory_qa_findings.v1"
RELEASE_QA_ASSEMBLER_VERSION = "release_qa_assembler_v1"

REQUIRED_RAW_INPUT_ROLES: tuple[str, ...] = (
    "source_assets",
    "dataset_assignments",
    "usage_records",
    "annotations",
    "binary_training_rows",
)
OPTIONAL_RAW_INPUT_ROLES: tuple[str, ...] = (
    "query_models",
    "query_records",
)
ALLOWED_RAW_INPUT_ROLES = frozenset(
    (*REQUIRED_RAW_INPUT_ROLES, *OPTIONAL_RAW_INPUT_ROLES)
)

RAW_INPUT_SCHEMA_BY_ROLE: Mapping[str, str] = {
    "source_assets": "floodguard.qa_input.source_assets.v1",
    "dataset_assignments": "floodguard.qa_input.dataset_assignments.v1",
    "usage_records": "floodguard.qa_input.usage_records.v1",
    "annotations": "floodguard.annotation_log.v1",
    "binary_training_rows": "floodguard.qa_input.binary_training_rows.v1",
    "query_models": "floodguard.qa_input.query_models.v1",
    "query_records": "floodguard.qa_input.query_records.v1",
}

_BOOLEAN_FIELDS = frozenset(
    {
        "processing_allowed",
        "label_derivation_allowed",
        "ml_label_derivation_allowed",
        "selected",
        "eligible_for_review_queue",
        "query_model_only",
        "eligible_for_decision_layer",
        "eligible_for_fpps",
        "eligible_for_warning",
        "eligible_for_training",
        "eligible_for_query_model_training",
        "selection_creates_flood_truth",
    }
)
_INTEGER_FIELDS = frozenset(
    {
        "label_code",
        "binary_target",
        "sampling_stratum_population",
        "sampling_stratum_quota",
    }
)
_FLOAT_FIELDS = frozenset({"inclusion_probability"})


class ReleaseQAError(ValueError):
    """Raised when raw release evidence cannot reproduce its QA receipt."""


def run_release_qa_from_raw_inputs(
    raw_input_paths: Mapping[str, str | Path],
) -> tuple[QAReport, dict[str, tuple[Any, ...]]]:
    """Load exact evidence files and run every in-scope release-QA lane.

    The five core roles are mandatory.  Query-model and query-selection files
    are optional because round zero can precede model training; when supplied,
    query records are checked both for the random-control design and for the
    permanent query-only/non-decision eligibility contract.
    """

    paths = _normalize_raw_input_paths(raw_input_paths)
    records = {
        role: tuple(_load_role_records(role, path))
        for role, path in paths.items()
    }
    query_safety_rows = (
        list(records.get("query_models", ()))
        + list(records.get("query_records", ()))
    )
    report = run_label_factory_qa(
        source_assets=records["source_assets"],
        dataset_assignments=records["dataset_assignments"],
        usage_records=records["usage_records"],
        query_models=(query_safety_rows if query_safety_rows else None),
        query_records=records.get("query_records"),
        annotations=records["annotations"],
        binary_training_rows=records["binary_training_rows"],
        require_complete_annotations=True,
    )
    _reject_duplicate_finding_keys(report)
    return report, records


def qa_report_content_sha256(report: QAReport) -> str:
    """Return the stable semantic digest used by the release-QA receipt."""

    if not isinstance(report, QAReport):
        raise ReleaseQAError("qa_report must be a QAReport.")
    rows = sorted(
        report.to_rows(),
        key=lambda row: (
            str(row["check_id"]),
            str(row["entity_id"]),
            str(row["severity"]),
        ),
    )
    return _canonical_json_sha256(rows)


def attach_raw_qa_provenance(
    base_receipt: Mapping[str, Any],
    *,
    qa_report: QAReport,
    raw_input_paths: Mapping[str, str | Path],
    raw_records: Mapping[str, Sequence[Any]] | None = None,
    qa_report_file_sha256: str,
) -> dict[str, Any]:
    """Add raw evidence, validator versions, safety fields, and a self-hash.

    ``base_receipt`` is the existing workflow receipt that already binds the
    reviewer pair, agreement evidence, reviewer-cell artifacts, raster lineage,
    and final rasters.  This function preserves those bindings and adds the
    missing code-owned raw-QA provenance.
    """

    if not isinstance(base_receipt, Mapping):
        raise ReleaseQAError("base_receipt must be a JSON object.")
    if base_receipt.get("artifact_schema") != RELEASE_QA_RECEIPT_SCHEMA:
        raise ReleaseQAError(
            "base_receipt must use artifact_schema="
            f"{RELEASE_QA_RECEIPT_SCHEMA!r}."
        )
    if "receipt_sha256" in base_receipt or "raw_input_artifacts" in base_receipt:
        raise ReleaseQAError(
            "base_receipt already contains raw-QA provenance or a self-hash."
        )
    if not report_is_release_ready(qa_report):
        failed = ", ".join(
            f"{finding.check_id}[{finding.entity_id}]"
            for finding in qa_report.blocking_failures
        )
        raise ReleaseQAError(
            "Raw release QA has blocking failures and cannot produce a passing "
            f"receipt: {failed}."
        )
    paths = _normalize_raw_input_paths(raw_input_paths)
    reproduced, loaded = run_release_qa_from_raw_inputs(paths)
    if raw_records is not None:
        supplied_roles = {str(role) for role in raw_records}
        if supplied_roles != set(paths):
            raise ReleaseQAError(
                "raw_records roles must exactly match raw_input_paths roles."
            )
    _verify_release_annotation_binding(base_receipt, loaded["annotations"])
    if qa_report_content_sha256(reproduced) != qa_report_content_sha256(qa_report):
        raise ReleaseQAError(
            "Supplied QA report does not reproduce from the exact raw inputs."
        )
    if base_receipt.get("qa_report_sha256") != qa_report_content_sha256(qa_report):
        raise ReleaseQAError(
            "Base QA receipt is not bound to the reproduced structured QA report."
        )
    report_file_hash = _required_sha256(
        qa_report_file_sha256, "qa_report_file_sha256"
    )
    artifacts = {
        role: {
            "file_name": path.name,
            "schema_version": RAW_INPUT_SCHEMA_BY_ROLE[role],
            "sha256": _hash_file(path),
            "row_count": len(loaded[role]),
        }
        for role, path in sorted(paths.items())
    }
    receipt = {
        **dict(base_receipt),
        "qa_assembler_version": RELEASE_QA_ASSEMBLER_VERSION,
        "qa_validator": "floodguard.label_factory.qa.run_label_factory_qa",
        "qa_validator_version": QA_VALIDATOR_VERSION,
        "qa_report_schema_version": RELEASE_QA_REPORT_SCHEMA,
        "qa_report_file_sha256": report_file_hash,
        "raw_input_artifacts": artifacts,
        "raw_input_roles_in_scope": sorted(artifacts),
        "query_models_in_scope": "query_models" in artifacts,
        "query_records_in_scope": "query_records" in artifacts,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }
    receipt["receipt_sha256"] = _canonical_json_sha256(receipt)
    return receipt


def write_release_qa_artifacts_from_raw(
    *,
    qa_report: QAReport,
    base_receipt: Mapping[str, Any],
    raw_input_paths: Mapping[str, str | Path],
    qa_report_path: str | Path,
    qa_receipt_path: str | Path,
) -> tuple[QAReport, dict[str, Any], Path, Path]:
    """Recompute and atomically write an immutable QA CSV/receipt pair."""

    paths = _normalize_raw_input_paths(raw_input_paths)
    reproduced, records = run_release_qa_from_raw_inputs(paths)
    _verify_release_annotation_binding(base_receipt, records["annotations"])
    if qa_report_content_sha256(reproduced) != qa_report_content_sha256(qa_report):
        raise ReleaseQAError(
            "Supplied QA report differs from the code-recomputed raw-input report."
        )
    report_bytes = _qa_report_csv_bytes(reproduced)
    report_hash = hashlib.sha256(report_bytes).hexdigest()
    receipt = attach_raw_qa_provenance(
        base_receipt,
        qa_report=reproduced,
        raw_input_paths=paths,
        raw_records=records,
        qa_report_file_sha256=report_hash,
    )
    report_target = Path(qa_report_path)
    receipt_target = Path(qa_receipt_path)
    _require_new_distinct_outputs(
        report_target,
        receipt_target,
        protected_inputs=tuple(paths.values()),
    )
    report_target.parent.mkdir(parents=True, exist_ok=True)
    receipt_target.parent.mkdir(parents=True, exist_ok=True)
    receipt_bytes = (
        json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")
    created: list[Path] = []
    try:
        with report_target.open("xb") as handle:
            handle.write(report_bytes)
        created.append(report_target)
        with receipt_target.open("xb") as handle:
            handle.write(receipt_bytes)
        created.append(receipt_target)
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return reproduced, receipt, report_target, receipt_target


def verify_release_qa_artifacts(
    *,
    qa_report: QAReport,
    qa_receipt: Mapping[str, Any],
    qa_report_path: str | Path,
    raw_input_paths: Mapping[str, str | Path],
) -> QAReport:
    """Re-run QA and verify the self-hashed receipt and every input byte.

    This is the freeze/revalidation entry point.  A legacy or hand-authored
    passing CSV is rejected because it lacks a valid self-hashed raw-input
    contract; a receipt with updated hashes is still rejected if rerunning the
    code over those bytes does not reproduce the report exactly.
    """

    if not isinstance(qa_receipt, Mapping):
        raise ReleaseQAError("qa_receipt must be a JSON object.")
    if qa_receipt.get("artifact_schema") != RELEASE_QA_RECEIPT_SCHEMA:
        raise ReleaseQAError(
            "QA receipt uses an unknown artifact_schema."
        )
    _verify_receipt_self_hash(qa_receipt)
    exact_versions = {
        "qa_assembler_version": RELEASE_QA_ASSEMBLER_VERSION,
        "qa_validator": "floodguard.label_factory.qa.run_label_factory_qa",
        "qa_validator_version": QA_VALIDATOR_VERSION,
        "qa_report_schema_version": RELEASE_QA_REPORT_SCHEMA,
    }
    for field, expected in exact_versions.items():
        if qa_receipt.get(field) != expected:
            raise ReleaseQAError(
                f"QA receipt {field} is unsupported; expected {expected!r}."
            )
    for field in (
        "eligible_for_decision_layer",
        "eligible_for_fpps",
        "eligible_for_warning",
    ):
        if qa_receipt.get(field) is not False:
            raise ReleaseQAError(f"QA receipt has unsafe {field}.")
    paths = _normalize_raw_input_paths(raw_input_paths)
    artifacts = qa_receipt.get("raw_input_artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != set(paths):
        raise ReleaseQAError(
            "QA receipt raw-input roles do not exactly match supplied raw artifacts."
        )
    declared_roles = qa_receipt.get("raw_input_roles_in_scope")
    if (
        not isinstance(declared_roles, list)
        or declared_roles != sorted(paths)
        or len(declared_roles) != len(set(declared_roles))
    ):
        raise ReleaseQAError(
            "QA receipt raw_input_roles_in_scope is not the exact sorted role set."
        )
    if qa_receipt.get("query_models_in_scope") is not (
        "query_models" in paths
    ) or qa_receipt.get("query_records_in_scope") is not (
        "query_records" in paths
    ):
        raise ReleaseQAError("QA receipt query-artifact scope flags are inconsistent.")
    reproduced, records = run_release_qa_from_raw_inputs(paths)
    _verify_release_annotation_binding(qa_receipt, records["annotations"])
    for role, path in paths.items():
        contract = artifacts.get(role)
        if not isinstance(contract, Mapping):
            raise ReleaseQAError(f"QA raw-input contract for {role} is invalid.")
        expected_contract = {
            "file_name": path.name,
            "schema_version": RAW_INPUT_SCHEMA_BY_ROLE[role],
            "sha256": _hash_file(path),
            "row_count": len(records[role]),
        }
        if dict(contract) != expected_contract:
            raise ReleaseQAError(
                f"QA raw-input artifact mismatch for role {role}."
            )
    report_path = Path(qa_report_path)
    if not report_path.is_file():
        raise ReleaseQAError(f"Structured QA report does not exist: {report_path}")
    report_bytes = report_path.read_bytes()
    if hashlib.sha256(report_bytes).hexdigest() != _required_sha256(
        qa_receipt.get("qa_report_file_sha256"), "qa_report_file_sha256"
    ):
        raise ReleaseQAError("Structured QA report file checksum mismatch.")
    if report_bytes != _qa_report_csv_bytes(reproduced):
        raise ReleaseQAError(
            "Structured QA report bytes do not exactly reproduce from raw evidence."
        )
    reproduced_hash = qa_report_content_sha256(reproduced)
    supplied_hash = qa_report_content_sha256(qa_report)
    if reproduced_hash != supplied_hash:
        raise ReleaseQAError(
            "Structured QA report does not reproduce from its raw evidence files."
        )
    if qa_receipt.get("qa_report_sha256") != reproduced_hash:
        raise ReleaseQAError(
            "QA receipt semantic report hash does not match recomputed findings."
        )
    if not report_is_release_ready(reproduced):
        failed = ", ".join(
            f"{finding.check_id}[{finding.entity_id}]"
            for finding in reproduced.blocking_failures
        )
        raise ReleaseQAError(
            f"Recomputed release QA has blocking failures: {failed}."
        )
    return reproduced


def report_is_release_ready(report: QAReport) -> bool:
    """Return true only for a non-empty report with no blocking failure."""

    return isinstance(report, QAReport) and bool(report.findings) and report.ready


def _normalize_raw_input_paths(
    raw_input_paths: Mapping[str, str | Path],
) -> dict[str, Path]:
    if not isinstance(raw_input_paths, Mapping):
        raise ReleaseQAError("raw_input_paths must map canonical roles to files.")
    roles = {str(role).strip() for role in raw_input_paths}
    unknown = sorted(roles - ALLOWED_RAW_INPUT_ROLES)
    missing = sorted(set(REQUIRED_RAW_INPUT_ROLES) - roles)
    if unknown or missing or len(roles) != len(raw_input_paths):
        raise ReleaseQAError(
            "Raw QA input roles are invalid; "
            f"missing={missing}, unknown_or_duplicate={unknown}."
        )
    normalized: dict[str, Path] = {}
    for raw_role, raw_path in raw_input_paths.items():
        role = str(raw_role).strip()
        path = Path(raw_path)
        if not path.is_file():
            raise ReleaseQAError(f"Raw QA input does not exist for {role}: {path}")
        normalized[role] = path
    resolved = [path.resolve() for path in normalized.values()]
    if len(resolved) != len(set(resolved)):
        raise ReleaseQAError("Each raw QA role must use a distinct source file.")
    return dict(sorted(normalized.items()))


def _load_role_records(role: str, path: Path) -> list[Any]:
    if role == "annotations":
        try:
            return list(load_annotation_log(path))
        except (AnnotationValidationError, OSError) as exc:
            raise ReleaseQAError(
                f"Could not load hash-chained annotation evidence {path}: {exc}"
            ) from exc
    rows = _load_tabular_or_json_rows(path)
    normalized = [_normalize_row(role, row, index) for index, row in enumerate(rows)]
    return normalized


def _load_tabular_or_json_rows(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"}:
        delimiter = "\t" if suffix == ".tsv" else ","
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                header = next(csv.reader(handle, delimiter=delimiter), None)
            if not header:
                return []
            if len(header) != len(set(header)):
                raise ReleaseQAError(f"Raw QA input has duplicate columns: {path}")
            frame = pd.read_csv(
                path,
                sep=delimiter,
                dtype=object,
                keep_default_na=False,
            )
        except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
            raise ReleaseQAError(f"Could not load raw QA table {path}: {exc}") from exc
        return [dict(row) for row in frame.to_dict(orient="records")]
    if suffix == ".json":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ReleaseQAError(f"Could not load raw QA JSON {path}: {exc}") from exc
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, Mapping) and isinstance(payload.get("records"), list):
            rows = payload["records"]
        elif isinstance(payload, Mapping):
            rows = [payload]
        else:
            raise ReleaseQAError(f"Raw QA JSON must contain object rows: {path}")
        if not all(isinstance(row, Mapping) for row in rows):
            raise ReleaseQAError(f"Raw QA JSON contains a non-object row: {path}")
        return [dict(row) for row in rows]
    if suffix in {".jsonl", ".ndjson"}:
        rows: list[dict[str, Any]] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise ReleaseQAError(f"Could not load raw QA JSONL {path}: {exc}") from exc
        for line_number, line in enumerate(lines, 1):
            if not line.strip():
                raise ReleaseQAError(
                    f"Raw QA JSONL contains a blank line at {path}:{line_number}."
                )
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ReleaseQAError(
                    f"Invalid raw QA JSONL at {path}:{line_number}."
                ) from exc
            if not isinstance(row, Mapping):
                raise ReleaseQAError(
                    f"Raw QA JSONL row is not an object at {path}:{line_number}."
                )
            rows.append(dict(row))
        return rows
    raise ReleaseQAError(
        f"Unsupported raw QA input format for {path}; use CSV, TSV, JSON, or JSONL."
    )


def _normalize_row(role: str, row: Mapping[str, Any], index: int) -> dict[str, Any]:
    normalized = {
        str(field): _normalize_scalar(str(field), value)
        for field, value in row.items()
    }
    if role == "query_models" and isinstance(normalized.get("safety"), Mapping):
        safety = dict(normalized["safety"])
        normalized.update(safety)
        if not str(normalized.get("model_id", "")).strip():
            normalized["model_id"] = str(
                normalized.get("run_id")
                or normalized.get("artifact_schema")
                or f"query_model[{index}]"
            )
    if role == "binary_training_rows" and not str(
        normalized.get("region_id", "")
    ).strip():
        query_id = str(normalized.get("query_region_id", "")).strip()
        cell_id = str(normalized.get("cell_id", "")).strip()
        if cell_id:
            normalized["region_id"] = (
                f"{query_id}::{cell_id}" if query_id else cell_id
            )
    return normalized


def _normalize_scalar(field: str, value: Any) -> Any:
    if field in _BOOLEAN_FIELDS:
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in {0, 1}:
            return bool(value)
        text = str(value).strip().lower()
        if text in {"true", "1", "yes"}:
            return True
        if text in {"false", "0", "no"}:
            return False
        return value
    if field in _INTEGER_FIELDS:
        if isinstance(value, bool):
            return value
        text = str(value).strip()
        try:
            number = int(text)
        except (TypeError, ValueError):
            return value
        return number if str(number) == text or text.startswith("+") else value
    if field in _FLOAT_FIELDS:
        if isinstance(value, bool):
            return value
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    return value


def _qa_report_csv_bytes(report: QAReport) -> bytes:
    buffer = io.StringIO(newline="")
    pd.DataFrame(report.to_rows()).to_csv(
        buffer,
        index=False,
        lineterminator="\n",
    )
    return buffer.getvalue().encode("utf-8")


def _reject_duplicate_finding_keys(report: QAReport) -> None:
    keys = [(finding.check_id, finding.entity_id) for finding in report.findings]
    if len(keys) != len(set(keys)):
        duplicates = sorted({key for key in keys if keys.count(key) > 1})
        raise ReleaseQAError(
            "Raw QA inputs produce duplicate check/entity findings; provide unique "
            f"release-grain entity ids: {duplicates}."
        )


def _verify_release_annotation_binding(
    receipt: Mapping[str, Any],
    annotations: Sequence[Any],
) -> None:
    declared_ids = receipt.get("source_annotation_ids")
    declared_hashes = receipt.get("source_annotation_sha256_by_id")
    if not isinstance(declared_ids, list) or not declared_ids:
        raise ReleaseQAError(
            "QA receipt must bind non-empty source_annotation_ids."
        )
    if (
        not all(isinstance(value, str) and value.strip() for value in declared_ids)
        or len(declared_ids) != len(set(declared_ids))
    ):
        raise ReleaseQAError("QA receipt source_annotation_ids are invalid.")
    if not isinstance(declared_hashes, Mapping) or set(declared_hashes) != set(
        declared_ids
    ):
        raise ReleaseQAError(
            "QA receipt source annotation hashes do not exactly match its ids."
        )
    records_by_id = {
        record.annotation_id: record
        for record in annotations
        if isinstance(record, AnnotationRecord)
    }
    missing = sorted(set(declared_ids) - set(records_by_id))
    if missing:
        raise ReleaseQAError(
            "Raw annotation evidence is missing release-bound annotations: "
            + ", ".join(missing)
        )
    for annotation_id in declared_ids:
        expected = _required_sha256(
            declared_hashes[annotation_id],
            f"source_annotation_sha256_by_id[{annotation_id}]",
        )
        if annotation_content_sha256(records_by_id[annotation_id]) != expected:
            raise ReleaseQAError(
                f"Raw annotation content does not match release binding for {annotation_id}."
            )


def _verify_receipt_self_hash(receipt: Mapping[str, Any]) -> None:
    supplied = _required_sha256(receipt.get("receipt_sha256"), "receipt_sha256")
    content = dict(receipt)
    content.pop("receipt_sha256", None)
    expected = _canonical_json_sha256(content)
    if supplied != expected:
        raise ReleaseQAError("QA receipt self-hash does not match canonical content.")


def _required_sha256(value: Any, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ReleaseQAError(f"{field_name} must be a lowercase SHA-256 digest.")
    return value


def _hash_file(path: Path) -> str:
    try:
        return file_sha256(path)
    except LabelsetVersionError as exc:
        raise ReleaseQAError(f"Could not hash release-QA artifact {path}: {exc}") from exc


def _canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_new_distinct_outputs(
    report_path: Path,
    receipt_path: Path,
    *,
    protected_inputs: Sequence[Path],
) -> None:
    outputs = (report_path.resolve(), receipt_path.resolve())
    if outputs[0] == outputs[1]:
        raise ReleaseQAError("QA report and receipt outputs must be distinct.")
    protected = {path.resolve() for path in protected_inputs}
    if any(path in protected for path in outputs):
        raise ReleaseQAError("QA outputs must not overwrite a raw evidence input.")
    existing = [str(path) for path in (report_path, receipt_path) if path.exists()]
    if existing:
        raise ReleaseQAError(
            "Release-QA outputs are immutable and cannot be overwritten: "
            + ", ".join(existing)
        )
