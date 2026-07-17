from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "docs/submission/2026-geohackathon"
SCRIPT = PACKAGE / "tools/build_submission.py"
SPEC = importlib.util.spec_from_file_location("floodguard_submission_build", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
submission = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(submission)


def test_owner_metadata_fails_closed_without_fabricated_values() -> None:
    metadata = json.loads((PACKAGE / "submission-metadata.json").read_text(encoding="utf-8"))

    errors = submission.metadata_errors(metadata, "f" * 40)

    assert any("team.name" in error for error in errors)
    assert any("team.members[0].skills" in error for error in errors)
    assert any("submission.demo_url" in error for error in errors)
    assert any("proposal_tag" in error for error in errors)
    assert any("portal_dataset_terms_reviewed" in error for error in errors)


def test_draft_render_is_explicitly_blocked_and_placeholder_free() -> None:
    metadata = json.loads((PACKAGE / "submission-metadata.json").read_text(encoding="utf-8"))

    rendered = submission.render_submission_markdown(metadata, draft=True)
    page = submission.markdown_to_html(rendered, draft=True)

    assert "DRAFT - RELEASE BLOCKED" in rendered
    assert "Owner-supplied identity required" in rendered
    assert "Non-operational" in rendered or "non-operational" in rendered
    assert not submission.LEGACY_PLACEHOLDER_RE.search(rendered)
    assert not submission.MUSTACHE_RE.search(page)


def test_markdown_renderer_handles_proposal_tables_lists_and_code() -> None:
    sample = """# Title

| Field | Value |
|---|---|
| Status | **Blocked** |

- one
- two

```text
pixel -> policy
```
"""

    page = submission.markdown_to_html(sample, draft=False)

    assert "<table>" in page
    assert "<strong>Blocked</strong>" in page
    assert "<ul>" in page
    assert "pixel -&gt; policy" in page


def test_submission_sources_contain_no_legacy_owner_placeholders() -> None:
    for path in PACKAGE.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert not submission.LEGACY_PLACEHOLDER_RE.search(text), path
        assert not submission.MUSTACHE_RE.search(text), path


def test_draft_build_writes_only_draft_named_outputs(tmp_path: Path) -> None:
    outputs = submission.build(draft=True, output_dir=tmp_path, emit_pdf=False)

    assert {path.suffix for path in outputs} == {".md", ".html"}
    assert all("DRAFT" in path.name for path in outputs)
    assert not (tmp_path / "FloodGuard_GeoHackathon_2026_Proposal.pdf").exists()


def test_html_renderer_cannot_create_final_submission_pdf(tmp_path: Path) -> None:
    try:
        submission.build(draft=False, output_dir=tmp_path, emit_pdf=True)
    except submission.SubmissionBuildError as exc:
        assert "retained polished DOCX" in str(exc)
    else:  # pragma: no cover - protects the fail-closed release boundary
        raise AssertionError("HTML renderer unexpectedly accepted a final PDF build")


def test_test_and_evidence_receipts_bind_to_tested_source_commit() -> None:
    tested = "a" * 40
    receipt = {
        "verification_status": "passed",
        "git_commit": tested,
        "generated_at": "2026-07-17T00:00:00Z",
        "suites": [
            {
                "name": "root",
                "result": "passed",
                "passed": 1,
                "skipped": 0,
                "source_commit": tested,
                "junit_sha256": "c" * 64,
            }
        ],
    }

    assert submission.test_receipt_errors(receipt, tested) == []
    assert any(
        "tested source commit" in error
        for error in submission.test_receipt_errors(receipt, "b" * 40)
    )


def test_pre_tag_mode_is_check_only(tmp_path: Path) -> None:
    try:
        submission.build(
            draft=False,
            output_dir=tmp_path,
            emit_pdf=False,
            check_only=False,
            pre_tag=True,
        )
    except submission.SubmissionBuildError as exc:
        assert "requires --check" in str(exc)
    else:  # pragma: no cover - protects the two-stage release boundary
        raise AssertionError("Pre-tag mode unexpectedly wrote release outputs")


def test_current_commit_is_its_own_valid_tested_ancestor() -> None:
    commit = submission.current_commit()

    assert submission._commit_exists(commit)
    assert submission._commit_is_ancestor(commit, commit)


def test_final_release_requires_source_derived_documents_and_inspection() -> None:
    errors = submission.final_release_artifact_errors(
        {"artifacts": []},
        require_clean_worktree=False,
    )

    assert any("final_proposal_docx" in error for error in errors)
    assert any("final_proposal_pdf" in error for error in errors)
    assert any("final_pdf_inspection_receipt" in error for error in errors)
