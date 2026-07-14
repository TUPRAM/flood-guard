from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

import pytest

from floodguard.label_factory.reviewer_workspace import (
    build_reviewer_practice_workspace,
)
from floodguard.label_factory.synthetic_learning import (
    build_synthetic_learning_package,
)


CREATED = datetime(2026, 7, 12, 4, 30, tzinfo=timezone.utc)
CASE_IDS = tuple(f"SYN-SAR-{index:03d}" for index in range(1, 21))
PANEL_FILENAMES = (
    "pre_vv.png",
    "event_vv.png",
    "pre_vh.png",
    "event_vh.png",
    "vv_change.png",
    "permanent_water.png",
    "slope.png",
    "landcover.png",
)
FALSE_SAFETY_FLAGS = (
    "formal_review_authorized",
    "formal_reviewer_calibration",
    "real_event_queries_used",
    "eligible_for_reviewer_calibration",
    "eligible_for_agreement",
    "eligible_for_consensus",
    "eligible_for_query_model_training",
    "eligible_for_model_evaluation",
    "eligible_for_decision_layer",
    "eligible_for_fpps",
    "eligible_for_warning",
)
FORBIDDEN_LEARNER_MANIFEST_KEYS = {
    "expected_primary",
    "rationale",
    "label_counts",
    "ambiguity_tags",
}
FORBIDDEN_FORMAL_DATA_MARKERS = (
    "TH-MAESAI-2024-09",
    "query_region_id",
    "weak_label",
    "weak_reference",
    "manual_weak_query_summary",
    "logistic_probability",
    "boosted_probability",
    "mean_logistic_probability",
    "mean_boosted_probability",
    "mean_committee_probability",
    "entropy_p90",
    "jensen_shannon_disagreement",
    "active_score",
    "selection_rank",
    "selection_reason",
    "calibration_reference",
    "authority_reference_private",
    "FG-RV-B-",
)


@pytest.fixture
def synthetic_cases(tmp_path: Path) -> Path:
    source = tmp_path / "synthetic_cases_v1"
    build_synthetic_learning_package(source, created_at_utc=CREATED)
    return source


class _ReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []
        self.landmarks: set[str] = set()
        self.tags: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values = dict(attrs)
        self.tags.append((tag, values))
        for attribute in ("src", "href"):
            value = values.get(attribute)
            if value:
                self.references.append(value)
        for attribute in ("id", "data-testid", "aria-label"):
            value = values.get(attribute)
            if value:
                self.landmarks.add(value.strip().lower())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _workspace_manifest(root: Path) -> tuple[Path, dict[str, object]]:
    preferred = root / "workspace_manifest.json"
    candidates = [preferred] if preferred.is_file() else sorted(root.glob("*.json"))
    for candidate in candidates:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and str(payload.get("artifact_schema", "")).startswith(
            "floodguard.reviewer_practice_workspace."
        ):
            return candidate, payload
    raise AssertionError("Reviewer workspace manifest was not written at output root.")


def _nested_values(payload: object, key: str) -> list[object]:
    values: list[object] = []
    if isinstance(payload, dict):
        for current_key, value in payload.items():
            if current_key == key:
                values.append(value)
            values.extend(_nested_values(value, key))
    elif isinstance(payload, list):
        for value in payload:
            values.extend(_nested_values(value, key))
    return values


def _all_sha256_values(payload: object) -> set[str]:
    matches: set[str] = set()
    if isinstance(payload, dict):
        for value in payload.values():
            matches.update(_all_sha256_values(value))
    elif isinstance(payload, list):
        for value in payload:
            matches.update(_all_sha256_values(value))
    elif isinstance(payload, str) and re.fullmatch(r"[0-9a-f]{64}", payload):
        matches.add(payload)
    return matches


def _find_single_asset(root: Path, case_id: str, filename: str) -> Path:
    matches = [
        path
        for path in root.rglob(filename)
        if case_id in path.relative_to(root).as_posix()
    ]
    assert len(matches) == 1, (
        f"Expected one copied {filename} for {case_id}; found "
        f"{[path.relative_to(root).as_posix() for path in matches]}"
    )
    return matches[0]


def test_builds_complete_offline_practice_workspace(
    tmp_path: Path,
    synthetic_cases: Path,
) -> None:
    formal_hold = tmp_path / "FORMAL_REVIEW_HOLD.json"
    formal_hold.write_text(
        json.dumps(
            {
                "artifact_schema": "floodguard.formal_review_hold.v1",
                "hold": True,
                "hold_reason": "Human roles and calibration are incomplete.",
                "eligible_for_query_model_training": False,
                "eligible_for_decision_layer": False,
                "eligible_for_fpps": False,
                "eligible_for_warning": False,
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "reviewer_practice_workspace"

    result = build_reviewer_practice_workspace(
        synthetic_cases,
        output,
        reviewer_display_name="I Putu Pramana Putra",
        created_at_utc=CREATED,
        formal_hold_path=formal_hold,
    )

    assert result.resolve() == output.resolve()
    index_path = output / "index.html"
    assert index_path.is_file()
    manifest_path, manifest = _workspace_manifest(output)
    assert manifest_path.parent == output
    assert manifest["artifact_schema"] == "floodguard.reviewer_practice_workspace.v1"
    assert manifest["case_count"] == 20
    assert tuple(manifest["case_ids"]) == CASE_IDS
    assert manifest["created_at_utc"] == "2026-07-12T04:30:00Z"
    assert manifest["reviewer_display_name"] == "I Putu Pramana Putra"

    practice_values = _nested_values(manifest, "practice_only")
    conceptual_values = _nested_values(manifest, "conceptual_teaching_only")
    hold_values = _nested_values(manifest, "formal_hold_active")
    assert practice_values and all(value is True for value in practice_values)
    assert conceptual_values and all(value is True for value in conceptual_values)
    assert hold_values and all(value is True for value in hold_values)
    for flag in FALSE_SAFETY_FLAGS:
        values = _nested_values(manifest, flag)
        assert values, f"Workspace manifest must explicitly declare {flag}."
        assert all(value is False for value in values), flag

    copied_hashes: set[str] = set()
    for case_id in CASE_IDS:
        for filename in PANEL_FILENAMES:
            copied = _find_single_asset(output, case_id, filename)
            source = synthetic_cases / case_id / filename
            assert copied.read_bytes() == source.read_bytes()
            copied_hashes.add(_sha256(copied))
        answer_name = f"{case_id}_labels.png"
        copied_answer = _find_single_asset(output, case_id, answer_name)
        source_answer = synthetic_cases / "answer_key" / answer_name
        assert copied_answer.read_bytes() == source_answer.read_bytes()
        copied_hashes.add(_sha256(copied_answer))

    assert len(list(output.rglob("*.png"))) >= 20 * 9
    manifest_hashes = _all_sha256_values(manifest)
    assert copied_hashes.issubset(manifest_hashes)
    assert _sha256(synthetic_cases / "manifest.json") in manifest_hashes


def test_workspace_is_relative_offline_and_contains_no_formal_data(
    tmp_path: Path,
    synthetic_cases: Path,
) -> None:
    output = tmp_path / "workspace"
    build_reviewer_practice_workspace(
        synthetic_cases,
        output,
        reviewer_display_name="Reviewer A practice",
        created_at_utc=CREATED,
    )
    _, manifest = _workspace_manifest(output)
    manifest_keys = set(_nested_keys(manifest))
    assert not FORBIDDEN_LEARNER_MANIFEST_KEYS.intersection(manifest_keys)

    text_files = [
        path
        for path in output.rglob("*")
        if path.is_file() and path.suffix.lower() in {".html", ".css", ".js", ".json", ".md"}
    ]
    assert text_files
    combined = "\n".join(path.read_text(encoding="utf-8") for path in text_files)
    assert str(tmp_path) not in combined
    assert str(synthetic_cases) not in combined
    assert not re.search(r"(?i)\bhttps?://|\bfile://|[a-z]:[\\/]", combined)
    for marker in FORBIDDEN_FORMAL_DATA_MARKERS:
        assert marker not in combined

    assert not list(output.rglob("*.tif"))
    assert not list(output.rglob("*.tiff"))
    assert not list(output.rglob("*.gpkg"))
    assert not list(output.rglob("*.geojson"))
    assert not list(output.rglob("*.csv"))

    for html_path in output.rglob("*.html"):
        parser = _ReferenceParser()
        parser.feed(html_path.read_text(encoding="utf-8"))
        for reference in parser.references:
            split = urlsplit(reference)
            assert not split.scheme and not split.netloc, reference
            if split.path in {"", "/"} or reference.startswith("#"):
                continue
            assert not split.path.startswith("/"), reference
            target = (html_path.parent / split.path).resolve()
            assert target.is_relative_to(output.resolve()), reference
            assert target.is_file(), reference


def _nested_keys(payload: object) -> list[str]:
    keys: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            keys.append(str(key))
            keys.extend(_nested_keys(value))
    elif isinstance(payload, list):
        for value in payload:
            keys.extend(_nested_keys(value))
    return keys


def test_workspace_html_exposes_reviewer_practice_controls(
    tmp_path: Path,
    synthetic_cases: Path,
) -> None:
    output = tmp_path / "workspace"
    build_reviewer_practice_workspace(
        synthetic_cases,
        output,
        reviewer_display_name="Reviewer A practice",
        created_at_utc=CREATED,
    )
    html = (output / "index.html").read_text(encoding="utf-8")
    parser = _ReferenceParser()
    parser.feed(html)
    application_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            output / "index.html",
            output / "workspace_data.js",
            output / "app.js",
        )
    )
    normalized = re.sub(r"\s+", " ", application_text.lower())

    required_landmark_fragments = (
        "formal-hold",
        "case-nav",
        "progress",
        "evidence",
        "annotation-canvas",
        "class-palette",
        "timer",
        "confidence",
        "ambiguity",
        "notes",
        "pre-lock-readiness",
        "lock",
        "reveal",
        "export",
    )
    for fragment in required_landmark_fragments:
        assert any(fragment in landmark for landmark in parser.landmarks), fragment

    tags = [tag for tag, _attrs in parser.tags]
    assert "canvas" in tags
    assert "dialog" in tags
    assert "textarea" in tags
    assert "select" in tags
    assert tags.count("button") >= 6

    required_phrase_alternatives = (
        ("practice only", "practice-only"),
        ("synthetic",),
        ("formal review hold", "formal-review hold"),
        ("pre vv", "pre-event vv"),
        ("event vv", "event-time vv"),
        ("pre vh", "pre-event vh"),
        ("event vh", "event-time vh"),
        ("vv change",),
        ("permanent water", "permanent-water"),
        ("slope",),
        ("land cover", "land-cover"),
        ("dry land", "dry_land"),
        ("temporary flood", "temporary_flood"),
        ("pre-existing water", "preexisting water"),
        ("uncertain water change", "uncertain_water_change"),
        ("unobservable",),
        ("unreviewed",),
        ("zoom",),
        ("undo",),
    )
    for alternatives in required_phrase_alternatives:
        assert any(phrase in normalized for phrase in alternatives), alternatives

    assert "localstorage" in normalized
    assert "locked_at_utc" in normalized
    assert "duration_seconds" in normalized
    assert "eligible_for_query_model_training" in normalized
    assert "eligible_for_model_evaluation" in normalized
    assert "eligible_for_decision_layer" in normalized
    assert "eligible_for_fpps" in normalized
    assert "eligible_for_warning" in normalized
    assert "window.confirm" not in normalized


def test_workspace_enforces_live_pre_lock_readiness(
    tmp_path: Path,
    synthetic_cases: Path,
) -> None:
    output = tmp_path / "workspace"
    build_reviewer_practice_workspace(
        synthetic_cases,
        output,
        reviewer_display_name="Reviewer A practice",
        created_at_utc=CREATED,
    )

    html = (output / "index.html").read_text(encoding="utf-8")
    app_js = (output / "app.js").read_text(encoding="utf-8")

    assert 'id="pre-lock-readiness"' in html
    assert 'id="readiness-summary"' in html
    assert 'id="readiness-checklist"' in html
    assert "These checks improve learning quality only" in html

    # Loading the default layer must not count as an explicit evidence visit.
    assert "function updateLayer(explicitVisit=false)" in app_js
    assert app_js.count("updateLayer(true)") == 2
    assert "const REQUIRED_LAYER_IDS = ['pre_vv','event_vv','pre_vh','event_vh','vv_change','permanent_water','slope','landcover'];" in app_js
    assert "all eight evidence layers must be explicitly visited" in app_js

    # Lock readiness must bind the selected assessment to painted cell codes.
    assert "attempt.primaryAssessment==='mixed_geometry'" in app_js
    assert "paintedCodes.size>=2" in app_js
    assert "attempt.labels.filter(code=>code===primaryCode).length" in app_js
    assert "selected primary assessment has no matching painted cells" in app_js

    # Whitespace does not satisfy the minimum reasoning requirement.
    assert "attempt.notes.replace(/\\s/g,'').length" in app_js
    assert "noteLength>=20" in app_js
    assert "reasoning note needs" in app_js

    # A new case must not silently bias the bulk-fill control toward flood (or
    # any other substantive class). Reviewers must choose class 0-4 first.
    assert "selectedCode:255" in app_js
    assert "fillButton.disabled=currentAttempt().locked||state.selectedCode===255" in app_js
    assert "Choose class 0–4 before filling unreviewed cells" in app_js

    # Both the initial lock action and final dialog confirmation re-check the
    # same live readiness contract.
    assert app_js.count("readinessItems(attempt).filter(item=>!item.ready)") == 2
    assert "byId('lock-attempt').disabled=attempt.locked||!allReady" in app_js


def test_workspace_rejects_overwrite_and_tampered_source(
    tmp_path: Path,
    synthetic_cases: Path,
) -> None:
    output = tmp_path / "workspace"
    build_reviewer_practice_workspace(
        synthetic_cases,
        output,
        reviewer_display_name="Reviewer A practice",
        created_at_utc=CREATED,
    )
    with pytest.raises((ValueError, FileExistsError), match="(?i)new|empty|exist|overwrite"):
        build_reviewer_practice_workspace(
            synthetic_cases,
            output,
            reviewer_display_name="Reviewer A practice",
            created_at_utc=CREATED,
        )

    source_asset = synthetic_cases / "SYN-SAR-004" / "event_vv.png"
    source_asset.write_bytes(source_asset.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="(?i)checksum|tamper|verify"):
        build_reviewer_practice_workspace(
            synthetic_cases,
            tmp_path / "tampered-output",
            reviewer_display_name="Reviewer A practice",
            created_at_utc=CREATED,
        )
