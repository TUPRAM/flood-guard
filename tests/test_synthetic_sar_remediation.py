from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from floodguard.label_factory.reviewer_workspace import (
    build_reviewer_practice_workspace,
)
from floodguard.label_factory.synthetic_remediation import (
    CASE_IDS,
    EXPECTED_FOCUSES,
    FALSE_SAFETY_FIELDS,
    GENERATOR_VERSION,
    SYNTHETIC_REMEDIATION_SCHEMA,
    SyntheticRemediationError,
    build_synthetic_remediation_package,
    verify_synthetic_remediation_package,
)


CREATED = datetime(2026, 7, 12, 8, 30, tzinfo=timezone.utc)


def test_build_and_verify_synthetic_remediation_package(tmp_path: Path) -> None:
    root = tmp_path / "synthetic_remediation_v1"
    manifest_path = build_synthetic_remediation_package(
        root,
        created_at_utc=CREATED,
    )
    verify_synthetic_remediation_package(root)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert payload["artifact_schema"] == SYNTHETIC_REMEDIATION_SCHEMA
    assert payload["generator_version"] == GENERATOR_VERSION
    assert payload["case_count"] == 12
    assert payload["case_ids"] == list(CASE_IDS)
    assert payload["design_focus"] == list(EXPECTED_FOCUSES)
    assert payload["practice_only"] is True
    assert payload["conceptual_teaching_only"] is True
    assert payload["physical_sar_simulator"] is False
    assert payload["answers_separated_from_learner_index"] is True
    assert all(payload[field] is False for field in FALSE_SAFETY_FIELDS)
    assert all(row["label_counts"]["255"] == 0 for row in payload["cases"])
    assert all(sum(row["label_counts"].values()) == 1024 for row in payload["cases"])
    assert len(payload["artifact_sha256"]) == 12 * 9 + 3

    for case_id in CASE_IDS:
        assert (root / case_id / "pre_vv.png").read_bytes().startswith(
            b"\x89PNG\r\n\x1a\n"
        )
        assert (
            root / "answer_key" / f"{case_id}_labels.png"
        ).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_remediation_cases_cover_diagnosed_class_distinctions(tmp_path: Path) -> None:
    root = tmp_path / "remediation"
    manifest_path = build_synthetic_remediation_package(
        root,
        created_at_utc=CREATED,
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_focus = {row["remediation_focus"]: row for row in payload["cases"]}

    assert set(by_focus) == set(EXPECTED_FOCUSES)
    assert by_focus["flooded_vegetation_supported_flood"]["label_counts"]["1"] > 0
    assert by_focus["flooded_vegetation_uncertain"]["label_counts"]["3"] > 0
    assert by_focus["wet_soil_agricultural_uncertain"]["label_counts"]["3"] > 0
    assert by_focus["temporal_mismatch_uncertain"]["label_counts"]["3"] > 0
    assert by_focus["misregistration_artifact"]["label_counts"]["4"] > 0
    assert by_focus["permanent_water_vs_artifact"]["label_counts"]["2"] > 0
    assert by_focus["permanent_water_vs_artifact"]["label_counts"]["4"] > 0
    assert by_focus["urban_ambiguity"]["label_counts"]["3"] > 0
    assert by_focus["urban_double_bounce_supported_flood"]["label_counts"]["1"] > 0
    assert by_focus["mixed_flood_boundary"]["label_counts"]["1"] > 0
    assert by_focus["mixed_flood_boundary"]["label_counts"]["3"] > 0
    assert by_focus["artifact_vs_dry"]["label_counts"]["0"] > 0
    assert by_focus["artifact_vs_dry"]["label_counts"]["4"] > 0
    assert by_focus["permanent_water_plus_new_flood"]["label_counts"]["1"] > 0
    assert by_focus["permanent_water_plus_new_flood"]["label_counts"]["2"] > 0

    complete = by_focus["complete_multiclass"]["label_counts"]
    assert all(complete[str(code)] > 0 for code in range(5))


def test_learner_index_does_not_expose_controlled_answers(tmp_path: Path) -> None:
    root = tmp_path / "remediation"
    manifest_path = build_synthetic_remediation_package(
        root,
        created_at_utc=CREATED,
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    learner_index = (root / "index.html").read_text(encoding="utf-8")
    answer_index = (root / "answer_key" / "index.html").read_text(
        encoding="utf-8"
    )

    assert "answer_key" not in learner_index
    for row in payload["cases"]:
        assert row["challenge"] not in learner_index
        assert row["rationale"] not in learner_index
        assert row["expected_primary"] not in learner_index
        assert row["challenge"] in answer_index
        assert row["rationale"] in answer_index


def test_synthetic_remediation_package_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_manifest = build_synthetic_remediation_package(
        first,
        created_at_utc=CREATED,
    )
    second_manifest = build_synthetic_remediation_package(
        second,
        created_at_utc=CREATED,
    )

    assert first_manifest.read_bytes() == second_manifest.read_bytes()
    assert (first / "SYN-REM-012" / "event_vh.png").read_bytes() == (
        second / "SYN-REM-012" / "event_vh.png"
    ).read_bytes()
    assert (
        first / "answer_key" / "SYN-REM-009_labels.png"
    ).read_bytes() == (
        second / "answer_key" / "SYN-REM-009_labels.png"
    ).read_bytes()


def test_synthetic_remediation_rejects_overwrite_tamper_and_naive_time(
    tmp_path: Path,
) -> None:
    root = tmp_path / "remediation"
    build_synthetic_remediation_package(root, created_at_utc=CREATED)
    with pytest.raises(SyntheticRemediationError, match="new or empty"):
        build_synthetic_remediation_package(root, created_at_utc=CREATED)

    target = root / "SYN-REM-007" / "event_vv.png"
    target.write_bytes(target.read_bytes() + b"tamper")
    with pytest.raises(SyntheticRemediationError, match="checksum"):
        verify_synthetic_remediation_package(root)

    with pytest.raises(SyntheticRemediationError, match="timezone-aware"):
        build_synthetic_remediation_package(
            tmp_path / "naive",
            created_at_utc=datetime(2026, 7, 12, 8, 30),
        )


def test_reviewer_workbench_accepts_remediation_schema_without_leaking_answers(
    tmp_path: Path,
) -> None:
    source = tmp_path / "remediation"
    build_synthetic_remediation_package(source, created_at_utc=CREATED)
    workspace = tmp_path / "reviewer_workspace"
    build_reviewer_practice_workspace(
        source,
        workspace,
        reviewer_display_name="Practice Reviewer",
        created_at_utc=CREATED,
    )

    manifest = json.loads(
        (workspace / "workspace_manifest.json").read_text(encoding="utf-8")
    )
    learner_data = (workspace / "workspace_data.js").read_text(encoding="utf-8")
    reveal_data = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((workspace / "assets" / "reveal").glob("*_answer.js"))
    )

    assert manifest["case_count"] == 12
    assert manifest["case_ids"] == list(CASE_IDS)
    assert manifest["source_package"]["artifact_schema"] == (
        SYNTHETIC_REMEDIATION_SCHEMA
    )
    assert "SYN-REM-001" in learner_data
    assert "expectedPrimary" not in learner_data
    assert "teachingRationale" not in learner_data
    assert "supported flooded-vegetation response" not in learner_data
    assert "supported flooded-vegetation response" in reveal_data
    assert all(manifest["safety"][field] is False for field in FALSE_SAFETY_FIELDS)
