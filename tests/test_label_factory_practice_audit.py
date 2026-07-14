from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from floodguard.label_factory.practice_audit import (
    SAFETY_FLAGS,
    PracticeAuditError,
    audit_reviewer_practice_exports,
)
from floodguard.label_factory.reviewer_workspace import _read_label_codes
from floodguard.label_factory.synthetic_learning import (
    build_synthetic_learning_package,
)
from floodguard.label_factory.synthetic_remediation import (
    build_synthetic_remediation_package,
)


AUDITED_AT = datetime(2026, 7, 12, 7, 0, tzinfo=timezone.utc)
WORKSPACE_ID = "FG-PRACTICE-0123456789ABCDEF"
REVIEWER = "I Putu Pramana Putra"
EXPECTED_PRIMARY = {
    "0 dry": "dry_land",
    "1 temporary_flood": "temporary_flood",
    "2 permanent_water": "permanent_or_preexisting_water",
    "3 uncertain": "uncertain_water_change",
    "4 unobservable": "unobservable_or_artifact",
    "mixed_geometry": "mixed_geometry",
}
LABEL_NAMES = {
    0: "dry_land",
    1: "temporary_flood",
    2: "permanent_or_preexisting_water",
    3: "uncertain_water_change",
    4: "unobservable_or_artifact",
}


@pytest.fixture(scope="module")
def base_exports(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("practice-audit-base")
    synthetic = root / "synthetic_cases_v1"
    build_synthetic_learning_package(
        synthetic,
        created_at_utc=datetime(2026, 7, 12, 4, 0, tzinfo=timezone.utc),
    )
    manifest = json.loads((synthetic / "manifest.json").read_text(encoding="utf-8"))

    session_cases: list[dict[str, object]] = []
    attempts: dict[str, dict[str, object]] = {}
    csv_rows: list[dict[str, object]] = []
    start = datetime(2026, 7, 12, 5, 0, tzinfo=timezone.utc)
    for index, source_case in enumerate(manifest["cases"]):
        case_id = source_case["case_id"]
        labels = _read_label_codes(
            synthetic / "answer_key" / f"{case_id}_labels.png"
        )
        started = start + timedelta(minutes=index)
        locked = started + timedelta(seconds=30)
        ambiguity = ["other"] if any(code in (3, 4) for code in labels) else []
        score = _score(labels, labels)
        case = {
            "practice_case_id": case_id,
            "locked": True,
            "started_at_utc": _utc(started),
            "locked_at_utc": _utc(locked),
            "duration_seconds": 30,
            "primary_assessment": EXPECTED_PRIMARY[source_case["expected_primary"]],
            "confidence": "medium",
            "ambiguity_reason_codes": ambiguity,
            "evidence_layers_viewed": ["pre_vv"],
            "notes": "",
            "practice_cell_codes": labels,
            "post_lock_feedback_revealed": True,
            "practice_score": score,
        }
        session_cases.append(case)
        attempts[case_id] = {
            "labels": labels,
            "history": [],
            "future": [],
            "locked": True,
            "revealed": True,
            "started_at_utc": case["started_at_utc"],
            "locked_at_utc": case["locked_at_utc"],
            "duration_seconds": 30.04,
            "confidence": "medium",
            "primaryAssessment": case["primary_assessment"],
            "ambiguity": ambiguity,
            "notes": "",
            "visitedLayers": ["pre_vv"],
            "score": score,
        }
        for cell_index, code in enumerate(labels):
            csv_rows.append(
                {
                    "practice_workspace_id": WORKSPACE_ID,
                    "practice_case_id": case_id,
                    "reviewer_display_name": REVIEWER,
                    "locked_at_utc": case["locked_at_utc"],
                    "duration_seconds": 30,
                    "confidence": "medium",
                    "row_index": cell_index // 32,
                    "column_index": cell_index % 32,
                    "practice_label_code": code,
                    "practice_label_name": LABEL_NAMES[code],
                    "post_lock_feedback_revealed": "true",
                }
            )

    completed = start + timedelta(minutes=21)
    session = {
        "artifact_schema": "floodguard.reviewer_practice_export.v1",
        "workspace_id": WORKSPACE_ID,
        "reviewer_display_name": REVIEWER,
        "exported_at_utc": _utc(completed),
        **SAFETY_FLAGS,
        "cases": session_cases,
    }
    draft = {
        "artifact_schema": "floodguard.reviewer_practice_draft.v1",
        "workspace_id": WORKSPACE_ID,
        "reviewer_display_name": REVIEWER,
        "saved_at_utc": _utc(completed),
        "case_index": 19,
        "attempts": attempts,
    }
    session_path = root / "floodguard_practice_session.json"
    draft_path = root / "floodguard_practice_draft.json"
    cells_path = root / "floodguard_practice_cells.csv"
    _write_json(session_path, session)
    _write_json(draft_path, draft)
    with cells_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(csv_rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(csv_rows)
    return {
        "synthetic": synthetic,
        "session": session_path,
        "draft": draft_path,
        "cells": cells_path,
    }


def test_writes_reproducible_practice_only_audit(
    tmp_path: Path, base_exports: dict[str, Path]
) -> None:
    inputs = _copy_exports(tmp_path, base_exports)
    output = tmp_path / "audit"

    written = audit_reviewer_practice_exports(
        inputs["session"],
        inputs["draft"],
        inputs["cells"],
        base_exports["synthetic"],
        output,
        audited_at_utc=AUDITED_AT,
    )

    assert written == output.resolve()
    assert {path.name for path in output.iterdir()} == {
        "summary.json",
        "case_metrics.csv",
        "confusion_matrix.csv",
        "input_hashes.json",
    }
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    observed_hash = summary.pop("summary_sha256")
    assert observed_hash == _canonical_hash(summary)
    assert summary["validation_status"] == "passed"
    assert summary["integrity_issue_count"] == 0
    assert summary["next_step_status"] == (
        "first_pass_complete_needs_targeted_remediation"
    )
    assert summary["formal_calibration_readiness_assessed"] is False
    assert summary["formal_calibration_status"] == "not_assessed_by_practice_audit"
    for key, expected in SAFETY_FLAGS.items():
        assert summary[key] is expected
    assert summary["summary_metrics"]["case_count"] == 20
    assert summary["summary_metrics"]["cell_count"] == 20_480
    assert summary["summary_metrics"]["overall_accuracy"] == 1.0
    assert summary["practice_heuristics"]["observed"][
        "reasoning_note_completion_rate"
    ] == 0.0
    assert summary["practice_heuristics"]["observed"][
        "all_layer_inspection_rate"
    ] == 0.0

    with (output / "case_metrics.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        case_rows = list(csv.DictReader(handle))
    with (output / "confusion_matrix.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        confusion_rows = list(csv.DictReader(handle))
    assert len(case_rows) == 20
    assert len(confusion_rows) == 25
    assert sum(int(row["cell_count"]) for row in confusion_rows) == 20_480
    assert all(row["reasoning_note_present"] == "false" for row in case_rows)

    input_manifest = json.loads(
        (output / "input_hashes.json").read_text(encoding="utf-8")
    )
    input_self_hash = input_manifest.pop("manifest_sha256")
    assert input_self_hash == _canonical_hash(input_manifest)
    assert input_manifest["input_artifact_sha256"]["session_json"] == _sha256(
        inputs["session"]
    )
    for filename, expected in summary["output_artifact_sha256"].items():
        assert _sha256(output / filename) == expected


@pytest.mark.parametrize(
    "failure",
    ("schema", "identity", "cell", "timestamp", "score", "safety"),
)
def test_fails_closed_on_export_mismatch(
    tmp_path: Path,
    base_exports: dict[str, Path],
    failure: str,
) -> None:
    inputs = _copy_exports(tmp_path, base_exports)
    session = json.loads(inputs["session"].read_text(encoding="utf-8"))
    draft = json.loads(inputs["draft"].read_text(encoding="utf-8"))
    if failure == "schema":
        session["artifact_schema"] = "unsupported"
        _write_json(inputs["session"], session)
    elif failure == "identity":
        draft["reviewer_display_name"] = "Different reviewer"
        _write_json(inputs["draft"], draft)
    elif failure == "cell":
        with inputs["cells"].open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        replacement = 1 if int(rows[0]["practice_label_code"]) != 1 else 0
        rows[0]["practice_label_code"] = str(replacement)
        rows[0]["practice_label_name"] = LABEL_NAMES[replacement]
        with inputs["cells"].open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    elif failure == "timestamp":
        session["cases"][0]["locked_at_utc"] = "2026-07-12T04:59:59Z"
        _write_json(inputs["session"], session)
    elif failure == "score":
        session["cases"][0]["practice_score"]["accuracy"] = 0.5
        _write_json(inputs["session"], session)
    elif failure == "safety":
        session["eligible_for_query_model_training"] = True
        _write_json(inputs["session"], session)
    output = tmp_path / "audit"

    with pytest.raises(PracticeAuditError):
        audit_reviewer_practice_exports(
            inputs["session"],
            inputs["draft"],
            inputs["cells"],
            base_exports["synthetic"],
            output,
            audited_at_utc=AUDITED_AT,
        )

    assert not output.exists()


def test_rejects_nonempty_output_directory(
    tmp_path: Path, base_exports: dict[str, Path]
) -> None:
    inputs = _copy_exports(tmp_path, base_exports)
    output = tmp_path / "audit"
    output.mkdir()
    (output / "existing.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(PracticeAuditError, match="new or empty"):
        audit_reviewer_practice_exports(
            inputs["session"],
            inputs["draft"],
            inputs["cells"],
            base_exports["synthetic"],
            output,
            audited_at_utc=AUDITED_AT,
        )

    assert (output / "existing.txt").read_text(encoding="utf-8") == "keep"


def test_audits_schema_governed_remediation_exports(tmp_path: Path) -> None:
    synthetic = tmp_path / "synthetic_remediation_v1"
    build_synthetic_remediation_package(
        synthetic,
        created_at_utc=datetime(2026, 7, 12, 8, 30, tzinfo=timezone.utc),
    )
    manifest = json.loads((synthetic / "manifest.json").read_text(encoding="utf-8"))
    exports = _write_perfect_exports(
        tmp_path,
        synthetic,
        manifest,
        start=datetime(2026, 7, 12, 9, 0, tzinfo=timezone.utc),
    )

    output = audit_reviewer_practice_exports(
        exports["session"],
        exports["draft"],
        exports["cells"],
        synthetic,
        tmp_path / "remediation-audit",
        audited_at_utc=datetime(2026, 7, 12, 10, 0, tzinfo=timezone.utc),
    )

    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["practice_stage"] == "targeted_remediation"
    assert summary["source_package_schema"] == (
        "floodguard.synthetic_sar_remediation_cases.v1"
    )
    assert summary["summary_metrics"]["case_count"] == 12
    assert summary["summary_metrics"]["cell_count"] == 12_288
    assert summary["next_step_status"] == (
        "remediation_complete_ready_for_real_data_orientation"
    )


def _write_perfect_exports(
    root: Path,
    synthetic: Path,
    manifest: dict[str, object],
    *,
    start: datetime,
) -> dict[str, Path]:
    session_cases: list[dict[str, object]] = []
    attempts: dict[str, dict[str, object]] = {}
    csv_rows: list[dict[str, object]] = []
    for index, source_case in enumerate(manifest["cases"]):
        assert isinstance(source_case, dict)
        case_id = str(source_case["case_id"])
        labels = _read_label_codes(synthetic / "answer_key" / f"{case_id}_labels.png")
        started = start + timedelta(minutes=index * 2)
        locked = started + timedelta(seconds=45)
        ambiguity = ["other"] if any(code in (3, 4) for code in labels) else []
        score = _score(labels, labels)
        case: dict[str, object] = {
            "practice_case_id": case_id,
            "locked": True,
            "started_at_utc": _utc(started),
            "locked_at_utc": _utc(locked),
            "duration_seconds": 45,
            "primary_assessment": EXPECTED_PRIMARY[str(source_case["expected_primary"])],
            "confidence": "medium",
            "ambiguity_reason_codes": ambiguity,
            "evidence_layers_viewed": [
                "pre_vv", "event_vv", "pre_vh", "event_vh", "vv_change",
                "permanent_water", "slope", "landcover",
            ],
            "notes": "All evidence layers support this synthetic teaching answer.",
            "practice_cell_codes": labels,
            "post_lock_feedback_revealed": True,
            "practice_score": score,
        }
        session_cases.append(case)
        attempts[case_id] = {
            "labels": labels,
            "history": [],
            "future": [],
            "locked": True,
            "revealed": True,
            "started_at_utc": case["started_at_utc"],
            "locked_at_utc": case["locked_at_utc"],
            "duration_seconds": 45,
            "confidence": "medium",
            "primaryAssessment": case["primary_assessment"],
            "ambiguity": ambiguity,
            "notes": case["notes"],
            "visitedLayers": case["evidence_layers_viewed"],
            "score": score,
        }
        for cell_index, code in enumerate(labels):
            csv_rows.append(
                {
                    "practice_workspace_id": WORKSPACE_ID,
                    "practice_case_id": case_id,
                    "reviewer_display_name": REVIEWER,
                    "locked_at_utc": case["locked_at_utc"],
                    "duration_seconds": 45,
                    "confidence": "medium",
                    "row_index": cell_index // 32,
                    "column_index": cell_index % 32,
                    "practice_label_code": code,
                    "practice_label_name": LABEL_NAMES[code],
                    "post_lock_feedback_revealed": "true",
                }
            )

    completed = start + timedelta(minutes=25)
    session = {
        "artifact_schema": "floodguard.reviewer_practice_export.v1",
        "workspace_id": WORKSPACE_ID,
        "reviewer_display_name": REVIEWER,
        "exported_at_utc": _utc(completed),
        **SAFETY_FLAGS,
        "cases": session_cases,
    }
    draft = {
        "artifact_schema": "floodguard.reviewer_practice_draft.v1",
        "workspace_id": WORKSPACE_ID,
        "reviewer_display_name": REVIEWER,
        "saved_at_utc": _utc(completed),
        "case_index": 11,
        "attempts": attempts,
    }
    session_path = root / "remediation_session.json"
    draft_path = root / "remediation_draft.json"
    cells_path = root / "remediation_cells.csv"
    _write_json(session_path, session)
    _write_json(draft_path, draft)
    with cells_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(csv_rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(csv_rows)
    return {"session": session_path, "draft": draft_path, "cells": cells_path}


def _copy_exports(tmp_path: Path, base: dict[str, Path]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for key in ("session", "draft", "cells"):
        destination = tmp_path / base[key].name
        shutil.copyfile(base[key], destination)
        result[key] = destination
    return result


def _score(selected: list[int], answer: list[int]) -> dict[str, int | float]:
    correct = true_positive = false_positive = false_negative = 0
    for predicted, truth in zip(selected, answer, strict=True):
        if predicted == truth:
            correct += 1
        if predicted == 1 and truth == 1:
            true_positive += 1
        elif predicted == 1:
            false_positive += 1
        elif truth == 1:
            false_negative += 1
    denominator = 2 * true_positive + false_positive + false_negative
    return {
        "accuracy": correct / len(answer),
        "temporary_flood_dice": (
            2 * true_positive / denominator if denominator else 1.0
        ),
        "correct_cells": correct,
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
    }


def _utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
