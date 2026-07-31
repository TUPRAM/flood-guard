from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from floodguard.label_factory.event_registry import EventRecord, SourceAssetRecord
from floodguard.label_factory.processing_alignment import (
    PROCESSING_ALIGNMENT_RECEIPT_SCHEMA,
    ProcessingAlignmentError,
    build_processing_alignment_receipt,
    load_processing_alignment_receipt,
    validate_processing_alignment_receipt,
    write_processing_alignment_receipt,
)
from label_factory_processing_fixtures import (
    synthetic_processing_evidence,
    synthetic_processing_receipt,
)
from test_label_factory_event_registry import event_row, valid_sources


def _records() -> tuple[tuple[EventRecord, ...], tuple[SourceAssetRecord, ...]]:
    return (
        (EventRecord.from_mapping(event_row()),),
        tuple(SourceAssetRecord.from_mapping(row) for row in valid_sources()),
    )


def test_receipt_rehashes_files_and_binds_complete_source_grid(tmp_path: Path) -> None:
    events, sources = _records()
    receipt = synthetic_processing_receipt(tmp_path, events, sources)

    assert receipt["artifact_schema"] == PROCESSING_ALIGNMENT_RECEIPT_SCHEMA
    assert receipt["source_asset_count"] == 2
    assert len(receipt["receipt_sha256"]) == 64
    assert {row["asset_id"] for row in receipt["assets"]} == {
        "S1-PRE-FIXTURE",
        "S1-EVENT-FIXTURE",
    }
    assert all(row["coverage_fraction"] == 1.0 for row in receipt["assets"])
    assert all(row["registration_error_pixels"] <= 0.5 for row in receipt["assets"])
    assert all(row["query_model_only"] is True for row in receipt["assets"])
    assert all(row["eligible_for_fpps"] is False for row in receipt["assets"])
    assert (
        validate_processing_alignment_receipt(
            receipt, events, sources, allow_ungoverned_fixture=True
        )
        == receipt
    )


def test_receipt_detects_processed_file_tampering(tmp_path: Path) -> None:
    events, sources = _records()
    evidence = synthetic_processing_evidence(tmp_path, events, sources)
    path = Path(str(evidence.loc[0, "processed_file_path"]))
    path.write_bytes(b"changed after expected hash")

    with pytest.raises(ProcessingAlignmentError, match="SHA-256 mismatch"):
        build_processing_alignment_receipt(
            events, sources, evidence, allow_ungoverned_fixture=True
        )


def test_receipt_requires_exact_nonstatic_coverage_and_common_grid(
    tmp_path: Path,
) -> None:
    events, sources = _records()
    evidence = synthetic_processing_evidence(tmp_path, events, sources)
    with pytest.raises(ProcessingAlignmentError, match="exactly cover"):
        build_processing_alignment_receipt(
            events,
            sources,
            evidence.iloc[:1],
            allow_ungoverned_fixture=True,
        )

    evidence = synthetic_processing_evidence(tmp_path / "mismatch", events, sources)
    evidence.loc[1, "width_pixels"] = 1024
    with pytest.raises(ProcessingAlignmentError, match="share one affine"):
        build_processing_alignment_receipt(
            events, sources, evidence, allow_ungoverned_fixture=True
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("registration_error_pixels", 0.51, "exceeds"),
        ("coverage_fraction", 0.99, "full coverage_fraction=1"),
        ("affine_b", 0.1, "north-up"),
        ("eligible_for_fpps", True, "unsafe"),
        ("rtc_terrain_correction_method", "unknown", "specific evidence"),
    ],
)
def test_receipt_fails_closed_on_alignment_and_safety_fields(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    events, sources = _records()
    evidence = synthetic_processing_evidence(tmp_path, events, sources)
    evidence.loc[0, field] = value

    with pytest.raises(ProcessingAlignmentError, match=message):
        build_processing_alignment_receipt(
            events, sources, evidence, allow_ungoverned_fixture=True
        )


def test_receipt_writer_is_immutable_and_loader_rejects_tampering(
    tmp_path: Path,
) -> None:
    events, sources = _records()
    receipt = synthetic_processing_receipt(tmp_path, events, sources)
    output = write_processing_alignment_receipt(receipt, tmp_path / "receipt.json")
    assert load_processing_alignment_receipt(output) == receipt
    with pytest.raises(ProcessingAlignmentError, match="already exists"):
        write_processing_alignment_receipt(receipt, output)

    payload = json.loads(output.read_text(encoding="utf-8"))
    payload["assets"][0]["registration_error_pixels"] = 0.3
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ProcessingAlignmentError, match="self-hash mismatch"):
        load_processing_alignment_receipt(tampered)


def test_receipt_cross_validation_rejects_changed_source_registry(
    tmp_path: Path,
) -> None:
    events, sources = _records()
    receipt = synthetic_processing_receipt(tmp_path, events, sources)
    changed_rows = deepcopy(valid_sources())
    changed_rows[0]["assumptions"] = "Changed source-registry evidence."
    changed_sources = tuple(
        SourceAssetRecord.from_mapping(row) for row in changed_rows
    )
    with pytest.raises(ProcessingAlignmentError, match="source-registry hash"):
        validate_processing_alignment_receipt(
            receipt,
            events,
            changed_sources,
            allow_ungoverned_fixture=True,
        )


def test_receipt_requires_governance_without_explicit_fixture_opt_in(
    tmp_path: Path,
) -> None:
    events, sources = _records()
    evidence = synthetic_processing_evidence(tmp_path, events, sources)

    with pytest.raises(ProcessingAlignmentError, match="governance clearance package"):
        build_processing_alignment_receipt(events, sources, evidence)


def test_fixture_opt_in_cannot_bypass_provider_conditioned_governance(
    tmp_path: Path,
) -> None:
    conditioned_event = event_row()
    conditioned_event["source_rights_status"] = "approved_with_provider_conditions"
    conditioned_event["validation_allowed"] = False
    conditioned_source_rows = deepcopy(valid_sources())
    for row in conditioned_source_rows:
        row["license_status"] = "approved_with_provider_conditions"
        row["redistribution_status"] = "YES_WITH_CONDITIONS"
    events = (EventRecord.from_mapping(conditioned_event),)
    sources = tuple(
        SourceAssetRecord.from_mapping(row) for row in conditioned_source_rows
    )
    evidence = synthetic_processing_evidence(tmp_path, events, sources)

    with pytest.raises(
        ProcessingAlignmentError,
        match="approved_with_provider_conditions registries require",
    ):
        build_processing_alignment_receipt(
            events,
            sources,
            evidence,
            allow_ungoverned_fixture=True,
        )


def test_processing_receipt_cli_help() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "build_label_factory_processing_receipt.py"),
            "--help",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "usage:" in result.stdout.lower()
    assert "processing-evidence" in result.stdout
    assert "governance-package" in result.stdout
