"""Guard the separate automated evidence files against invented human work."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".csv", ".json", ".md", ".py", ".ts", ".tsx"}


def _automated_files() -> list[Path]:
    paths = [ROOT / "scripts" / "acquire_earth_search_mae_sai_reference.py"]
    for pattern in (
        "docs/proposal_execution/automated_track/**/*",
        "src/floodguard/*automated*.py",
        "scripts/*automated*.py",
        "outputs/*automated*",
        "outputs/earth_search_mae_sai_sentinel2_reference_assets.csv",
        "tests/test_automated*.py",
        "tests/test_acquire_earth_search_mae_sai_reference.py",
    ):
        paths.extend(ROOT.glob(pattern))
    return sorted({path for path in paths if path.is_file() and path.suffix in TEXT_SUFFIXES})


def _human_reviewed_true(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            (key == "human_reviewed" and field is True) or _human_reviewed_true(field)
            for key, field in value.items()
        )
    if isinstance(value, list):
        return any(_human_reviewed_true(item) for item in value)
    return False


def test_automated_files_contain_no_fabricated_human_evidence() -> None:
    files = _automated_files()
    assert files, "No automated-track files were found to check."
    forbidden = tuple("FG-" + role + "-" for role in ("HUM", "RA", "RV", "ADJ"))
    for path in files:
        content = path.read_text(encoding="utf-8")
        assert not any(prefix in content for prefix in forbidden), path
        if path.suffix == ".json":
            assert not _human_reviewed_true(json.loads(content)), path
        elif path.suffix == ".csv":
            with path.open(newline="", encoding="utf-8") as stream:
                for row in csv.DictReader(stream):
                    assert row.get("human_reviewed", "").strip().lower() != "true", path
