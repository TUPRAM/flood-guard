from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from floodguard.label_factory.synthetic_learning import (
    SyntheticLearningError,
    build_synthetic_learning_package,
    verify_synthetic_learning_package,
)


CREATED = datetime(2026, 7, 11, 8, 0, tzinfo=timezone.utc)


def test_build_and_verify_synthetic_learning_package(tmp_path: Path) -> None:
    root = tmp_path / "synthetic_cases_v1"
    manifest_path = build_synthetic_learning_package(root, created_at_utc=CREATED)
    verify_synthetic_learning_package(root)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert payload["case_count"] == 20
    assert payload["case_ids"][0] == "SYN-SAR-001"
    assert payload["case_ids"][-1] == "SYN-SAR-020"
    assert payload["conceptual_teaching_only"] is True
    assert payload["physical_sar_simulator"] is False
    assert payload["formal_reviewer_calibration"] is False
    assert payload["real_event_queries_used"] is False
    assert payload["eligible_for_query_model_training"] is False
    assert payload["eligible_for_decision_layer"] is False
    assert payload["eligible_for_fpps"] is False
    assert payload["eligible_for_warning"] is False
    assert (root / "index.html").is_file()
    assert (root / "answer_key" / "index.html").is_file()
    assert (root / "SYN-SAR-001" / "pre_vv.png").read_bytes().startswith(
        b"\x89PNG\r\n\x1a\n"
    )


def test_synthetic_learning_package_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_manifest = build_synthetic_learning_package(first, created_at_utc=CREATED)
    second_manifest = build_synthetic_learning_package(second, created_at_utc=CREATED)

    assert first_manifest.read_bytes() == second_manifest.read_bytes()
    assert (first / "SYN-SAR-020" / "vv_change.png").read_bytes() == (
        second / "SYN-SAR-020" / "vv_change.png"
    ).read_bytes()


def test_synthetic_learning_package_rejects_overwrite_and_tamper(
    tmp_path: Path,
) -> None:
    root = tmp_path / "synthetic_cases_v1"
    build_synthetic_learning_package(root, created_at_utc=CREATED)
    with pytest.raises(SyntheticLearningError, match="new or empty"):
        build_synthetic_learning_package(root, created_at_utc=CREATED)

    target = root / "SYN-SAR-001" / "pre_vv.png"
    target.write_bytes(target.read_bytes() + b"tamper")
    with pytest.raises(SyntheticLearningError, match="checksum"):
        verify_synthetic_learning_package(root)


def test_synthetic_learning_requires_utc_timestamp(tmp_path: Path) -> None:
    with pytest.raises(SyntheticLearningError, match="timezone-aware"):
        build_synthetic_learning_package(
            tmp_path / "synthetic_cases_v1",
            created_at_utc=datetime(2026, 7, 11, 8, 0),
        )
