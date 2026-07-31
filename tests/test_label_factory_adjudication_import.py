from __future__ import annotations

import csv
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from floodguard.label_factory.adjudication import (
    AdjudicationError,
    append_adjudication_record,
    append_adjudication_records,
    build_adjudication_queue,
    build_adjudication_record,
    load_adjudication_log,
    pair_locked_annotations,
)
from floodguard.label_factory.adjudication_import import (
    ADJUDICATION_IMPORT_RECEIPT_SCHEMA,
    COMPLETED_ADJUDICATION_COLUMNS,
    AdjudicationImportError,
    import_completed_adjudications,
)
from floodguard.label_factory.annotations import (
    AnnotationRecord,
    LabelClass,
    append_annotation_record,
)
from floodguard.label_factory.review_workflow import write_adjudication_queue_csv


def test_import_exact_queue_coverage_appends_chain_and_writes_safe_receipt(
    tmp_path: Path,
) -> None:
    annotation_log, queue_path, pairs, queue = _source_artifacts(tmp_path)
    completed = tmp_path / "completed.csv"
    _write_completed(
        completed,
        [
            _completed_row(
                queue[0].queue_id,
                "ADJ-001",
                outcome="accept_a",
                reasons="class_disagreement",
            ),
            _completed_row(
                queue[1].queue_id,
                "ADJ-002",
                outcome="redraw",
                reasons="geometry_disagreement",
                final_primary_class="1",
                final_geometry="POLYGON ((20 0, 21 0, 21 1, 20 1, 20 0))",
            ),
        ],
    )
    log = tmp_path / "adjudications.jsonl"
    receipt_path = tmp_path / "import-receipt.json"

    receipt = import_completed_adjudications(
        completed,
        adjudication_queue=queue_path,
        annotation_log=annotation_log,
        adjudication_log=log,
        receipt_json=receipt_path,
        reviewer_a_id="RV-A",
        reviewer_b_id="RV-B",
        imported_at_utc=_utc(4),
    )

    records = load_adjudication_log(log)
    assert len(records) == 2
    assert records[0].final_primary_class is pairs[0].reviewer_a.primary_class
    assert records[0].final_geometry == pairs[0].reviewer_a.geometry
    assert records[1].final_primary_class is LabelClass.TEMPORARY_FLOOD
    assert receipt.imported_count == 2
    assert receipt.remaining_open_queue_count == 0
    assert receipt.source_annotation_ids == ("ANN-A-1", "ANN-A-2", "ANN-B-1", "ANN-B-2")
    assert len(receipt.appended_record_sha256) == 2

    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert payload["artifact_schema"] == ADJUDICATION_IMPORT_RECEIPT_SCHEMA
    assert payload["coverage_complete"] is True
    assert payload["report_only"] is True
    assert payload["requires_frozen_labelset"] is True
    assert payload["eligible_for_query_model_training"] is False
    assert payload["eligible_for_decision_layer"] is False
    assert payload["eligible_for_fpps"] is False
    assert payload["eligible_for_warning"] is False
    unsigned = {key: value for key, value in payload.items() if key != "receipt_sha256"}
    assert payload["receipt_sha256"] == _canonical_sha256(unsigned)

    with pytest.raises(AdjudicationImportError, match="already exists"):
        import_completed_adjudications(
            completed,
            adjudication_queue=queue_path,
            annotation_log=annotation_log,
            adjudication_log=log,
            receipt_json=receipt_path,
            reviewer_a_id="RV-A",
            reviewer_b_id="RV-B",
            imported_at_utc=_utc(4),
        )


def test_import_rejects_partial_queue_coverage_without_writing_outputs(
    tmp_path: Path,
) -> None:
    annotation_log, queue_path, _pairs, queue = _source_artifacts(tmp_path)
    completed = tmp_path / "partial.csv"
    _write_completed(
        completed,
        [_completed_row(queue[0].queue_id, "ADJ-001", outcome="accept_b")],
    )
    log = tmp_path / "adjudications.jsonl"
    receipt = tmp_path / "receipt.json"

    with pytest.raises(AdjudicationImportError, match="exactly cover"):
        import_completed_adjudications(
            completed,
            adjudication_queue=queue_path,
            annotation_log=annotation_log,
            adjudication_log=log,
            receipt_json=receipt,
            reviewer_a_id="RV-A",
            reviewer_b_id="RV-B",
            imported_at_utc=_utc(4),
        )

    assert not log.exists()
    assert not receipt.exists()


def test_import_validates_queue_source_hashes_before_append(tmp_path: Path) -> None:
    annotation_log, queue_path, _pairs, queue = _source_artifacts(tmp_path)
    rows = list(csv.DictReader(queue_path.open(encoding="utf-8")))
    rows[0]["reviewer_a_sha256"] = "0" * 64
    with queue_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    completed = tmp_path / "completed.csv"
    _write_completed(
        completed,
        [
            _completed_row(queue[0].queue_id, "ADJ-001", outcome="accept_a"),
            _completed_row(queue[1].queue_id, "ADJ-002", outcome="accept_b"),
        ],
    )

    with pytest.raises(AdjudicationError, match="does not match its source"):
        import_completed_adjudications(
            completed,
            adjudication_queue=queue_path,
            annotation_log=annotation_log,
            adjudication_log=tmp_path / "adjudications.jsonl",
            receipt_json=tmp_path / "receipt.json",
            reviewer_a_id="RV-A",
            reviewer_b_id="RV-B",
            imported_at_utc=_utc(4),
        )


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"outcome": "approve"}, "outcome must be one of"),
        ({"outcome": "redraw", "final_primary_class": "1"}, "redraw requires"),
        ({"outcome": "accept_a", "final_primary_class": "0"}, "must leave final"),
        ({"adjudicator_id": "RV-A"}, "must differ from reviewers"),
        ({"resolution_reason_codes": "made_up_reason"}, "unknown resolution reason"),
        ({"locked_at_utc": "2024-09-18T01:00:00Z"}, "must not precede"),
    ],
)
def test_import_rejects_invalid_human_resolution_fields_before_append(
    tmp_path: Path,
    updates: dict[str, str],
    message: str,
) -> None:
    annotation_log, queue_path, _pairs, queue = _source_artifacts(tmp_path)
    first = _completed_row(queue[0].queue_id, "ADJ-001", outcome="accept_a")
    first.update(updates)
    completed = tmp_path / "completed.csv"
    _write_completed(
        completed,
        [first, _completed_row(queue[1].queue_id, "ADJ-002", outcome="accept_b")],
    )
    log = tmp_path / "adjudications.jsonl"

    with pytest.raises((AdjudicationImportError, AdjudicationError), match=message):
        import_completed_adjudications(
            completed,
            adjudication_queue=queue_path,
            annotation_log=annotation_log,
            adjudication_log=log,
            receipt_json=tmp_path / "receipt.json",
            reviewer_a_id="RV-A",
            reviewer_b_id="RV-B",
            imported_at_utc=_utc(4),
        )

    assert not log.exists()


def test_batch_append_rejects_duplicate_ids_without_partial_write(tmp_path: Path) -> None:
    _annotation_log, _queue_path, pairs, queue = _source_artifacts(tmp_path)
    first = build_adjudication_record(
        queue[0],
        pairs[0],
        adjudication_id="ADJ-DUPLICATE",
        adjudicator_id="RV-C",
        outcome="accept_a",
        ambiguity_reason_codes=("class_disagreement",),
        resolved_at_utc=_utc(2),
        locked_at_utc=_utc(3),
        protocol_version="protocol_v1",
    )
    second = build_adjudication_record(
        queue[1],
        pairs[1],
        adjudication_id="ADJ-SECOND",
        adjudicator_id="RV-C",
        outcome="accept_b",
        ambiguity_reason_codes=("class_disagreement",),
        resolved_at_utc=_utc(2),
        locked_at_utc=_utc(3),
        protocol_version="protocol_v1",
    )
    log = tmp_path / "batch.jsonl"

    with pytest.raises(AdjudicationError, match="already exists"):
        append_adjudication_records(
            log,
            (first, replace(second, adjudication_id=first.adjudication_id)),
        )

    assert not log.exists()


def test_import_can_finish_only_the_exact_remaining_open_queue(tmp_path: Path) -> None:
    annotation_log, queue_path, pairs, queue = _source_artifacts(tmp_path)
    existing = build_adjudication_record(
        queue[0],
        pairs[0],
        adjudication_id="ADJ-EXISTING",
        adjudicator_id="RV-C",
        outcome="accept_a",
        ambiguity_reason_codes=("class_disagreement",),
        resolved_at_utc=_utc(2),
        locked_at_utc=_utc(3),
        protocol_version="protocol_v1",
    )
    log = tmp_path / "adjudications.jsonl"
    append_adjudication_record(log, existing)
    completed = tmp_path / "remaining.csv"
    _write_completed(
        completed,
        [_completed_row(queue[1].queue_id, "ADJ-NEW", outcome="accept_b")],
    )

    receipt = import_completed_adjudications(
        completed,
        adjudication_queue=queue_path,
        annotation_log=annotation_log,
        adjudication_log=log,
        receipt_json=tmp_path / "receipt.json",
        reviewer_a_id="RV-A",
        reviewer_b_id="RV-B",
        imported_at_utc=_utc(4),
    )

    assert receipt.previously_resolved_count == 1
    assert receipt.open_queue_count_before == 1
    assert receipt.imported_adjudication_ids == ("ADJ-NEW",)
    assert len(load_adjudication_log(log)) == 2


def test_adjudication_import_cli_help_and_blocked_exit(tmp_path: Path) -> None:
    script = Path(__file__).parents[1] / "scripts" / "import_label_factory_adjudications.py"
    help_run = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_run.returncode == 0
    assert "--completed-adjudications" in help_run.stdout
    assert "--receipt-json" in help_run.stdout

    blocked = subprocess.run(
        [
            sys.executable,
            str(script),
            "--completed-adjudications",
            str(tmp_path / "missing-completed.csv"),
            "--adjudication-queue",
            str(tmp_path / "missing-queue.csv"),
            "--annotation-log",
            str(tmp_path / "missing-annotations.jsonl"),
            "--reviewer-a-id",
            "RV-A",
            "--reviewer-b-id",
            "RV-B",
            "--adjudication-log",
            str(tmp_path / "adjudications.jsonl"),
            "--receipt-json",
            str(tmp_path / "receipt.json"),
            "--imported-at-utc",
            "2024-09-18T04:00:00Z",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert blocked.returncode == 2
    assert "BLOCKED:" in blocked.stderr


def _source_artifacts(tmp_path: Path):
    annotation_log = tmp_path / "annotations.jsonl"
    records: list[AnnotationRecord] = []
    for query_number in (1, 2):
        records.extend(
            [
                _annotation(
                    f"ANN-A-{query_number}",
                    "RV-A",
                    query_number,
                    primary_class=LabelClass.DRY_LAND,
                ),
                _annotation(
                    f"ANN-B-{query_number}",
                    "RV-B",
                    query_number,
                    primary_class=LabelClass.TEMPORARY_FLOOD,
                ),
            ]
        )
    for record in records:
        append_annotation_record(annotation_log, record)
    pairs = pair_locked_annotations(
        records,
        reviewer_a_id="RV-A",
        reviewer_b_id="RV-B",
    )
    queue = build_adjudication_queue(pairs, created_at_utc=_utc(1))
    assert len(queue) == 2
    queue_path = tmp_path / "queue.csv"
    write_adjudication_queue_csv(queue, queue_path)
    return annotation_log, queue_path, pairs, queue


def _annotation(
    annotation_id: str,
    reviewer_id: str,
    query_number: int,
    *,
    primary_class: LabelClass,
) -> AnnotationRecord:
    started = datetime(2024, 9, 17, 0, 0, tzinfo=timezone.utc)
    offset = query_number * 10
    return AnnotationRecord(
        annotation_id=annotation_id,
        event_id="TH-MAESAI-2024-09",
        tile_id=f"TILE-{query_number}",
        query_region_id=f"QUERY-{query_number}",
        reviewer_id=reviewer_id,
        reviewer_revision=1,
        primary_class=primary_class,
        confidence="high",
        ambiguity_reason_codes=(),
        evidence_layers_used=("pre_vv", "post_vv", "dem"),
        review_complete=True,
        reviewed_extent=(
            f"POLYGON (({offset} 0, {offset + 2} 0, {offset + 2} 2, "
            f"{offset} 2, {offset} 0))"
        ),
        geometry=(
            f"POLYGON (({offset} 0, {offset + 1} 0, {offset + 1} 1, "
            f"{offset} 1, {offset} 0))"
        ),
        review_started_at=started,
        review_finished_at=started + timedelta(minutes=10),
        protocol_version="protocol_v1",
        tool_version="qgis_v1",
        model_predictions_visible=False,
        other_reviewer_annotations_visible=False,
        created_at_utc=started + timedelta(minutes=11),
        locked_at_utc=started + timedelta(minutes=12),
    )


def _completed_row(
    queue_id: str,
    adjudication_id: str,
    *,
    outcome: str,
    reasons: str = "class_disagreement",
    final_primary_class: str = "",
    final_geometry: str = "",
) -> dict[str, str]:
    return {
        "queue_id": queue_id,
        "adjudication_id": adjudication_id,
        "adjudicator_id": "RV-C",
        "outcome": outcome,
        "resolution_reason_codes": reasons,
        "final_primary_class": final_primary_class,
        "final_geometry": final_geometry,
        "notes": "Human adjudicator reviewed both locked submissions.",
        "protocol_version": "protocol_v1",
        "resolved_at_utc": "2024-09-18T02:00:00Z",
        "locked_at_utc": "2024-09-18T03:00:00Z",
    }


def _write_completed(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COMPLETED_ADJUDICATION_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _utc(hour: int) -> datetime:
    return datetime(2024, 9, 18, hour, 0, tzinfo=timezone.utc)


def _canonical_sha256(value: dict[str, object]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
