"""Build the FloodGuard proposal from reviewed Markdown and owner metadata.

The final build is deliberately fail-closed. Draft mode exists only for layout
review and visibly labels every output as blocked/non-operational.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Mapping
from urllib.parse import urlparse
import zipfile


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
METADATA_PATH = PACKAGE_ROOT / "submission-metadata.json"
PROPOSAL_PATH = PACKAGE_ROOT / "proposal.md"
TEST_RECEIPT_PATH = PACKAGE_ROOT / "evidence/test-results.json"
EVIDENCE_PATH = PACKAGE_ROOT / "evidence/proposal-evidence.json"
EVIDENCE_TEMPLATE_PATH = PACKAGE_ROOT / "evidence/proposal-evidence.template.json"
FINAL_STEM = "FloodGuard_GeoHackathon_2026_Proposal"
FINAL_DOCX_PATH = PACKAGE_ROOT / "release" / f"{FINAL_STEM}.docx"
FINAL_PDF_PATH = PACKAGE_ROOT / "release" / f"{FINAL_STEM}.pdf"
FINAL_PDF_INSPECTION_PATH = PACKAGE_ROOT / "release" / "final-pdf-inspection.json"
SOURCE_DOCX_PATH = PACKAGE_ROOT / "source" / f"{FINAL_STEM}.docx"
SOURCE_PDF_PATH = PACKAGE_ROOT / "source" / f"{FINAL_STEM}.pdf"
PRIVATE_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/]|\\\\|file://|/(?:Users|home|root|tmp|var|private)/)",
    re.IGNORECASE,
)
LEGACY_PLACEHOLDER_RE = re.compile(
    r"\[(?:TEAM NAME|INSTITUTION(?: / SCHOOL / UNIVERSITY)?|MEMBER [123]|"
    r"PRIMARY CONTACT (?:NAME|EMAIL|PHONE)|ADVISER[^\]]*)\]",
    re.IGNORECASE,
)
MUSTACHE_RE = re.compile(r"\{\{[^{}]+\}\}")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class SubmissionBuildError(ValueError):
    """Raised when release evidence or metadata is incomplete or unsafe."""


def load_json(path: Path) -> dict[str, Any]:
    """Load one JSON object with a useful failure boundary."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SubmissionBuildError(f"Cannot read valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise SubmissionBuildError(f"JSON root must be an object: {path}")
    return value


def current_commit(repository_root: Path = REPOSITORY_ROOT) -> str:
    """Return the exact current Git commit."""

    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    value = completed.stdout.strip().lower()
    if not COMMIT_RE.fullmatch(value):
        raise SubmissionBuildError("Git did not return a full lowercase commit hash.")
    return value


def metadata_errors(
    metadata: Mapping[str, Any],
    packaging_commit: str,
    *,
    require_tag: bool = True,
    repository_root: Path = REPOSITORY_ROOT,
) -> list[str]:
    """Return every owner/release field that blocks a final build.

    ``submission.repository_commit`` is the immutable source commit on which
    the archived tests and GeoAI proof ran. It must exist and be an ancestor of
    the packaging commit, but it cannot equal a commit that also contains its
    own receipt. The proposal tag is checked only in the post-tag pass.
    """

    errors: list[str] = []
    if metadata.get("release_status") != "ready":
        errors.append("release_status must be 'ready'")
    team = _mapping(metadata.get("team"), "team", errors)
    _required_text(team.get("name"), "team.name", errors)
    _required_text(team.get("institution"), "team.institution", errors)
    contact = _mapping(team.get("primary_contact"), "team.primary_contact", errors)
    _required_text(contact.get("name"), "team.primary_contact.name", errors)
    email = _required_text(contact.get("email"), "team.primary_contact.email", errors)
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        errors.append("team.primary_contact.email must be a valid email")
    _required_text(contact.get("phone"), "team.primary_contact.phone", errors)

    members = team.get("members")
    if not isinstance(members, list) or len(members) != 3:
        errors.append("team.members must contain exactly three members")
    else:
        for index, raw in enumerate(members):
            member = _mapping(raw, f"team.members[{index}]", errors)
            _required_text(member.get("full_name"), f"team.members[{index}].full_name", errors)
            _required_text(member.get("role"), f"team.members[{index}].role", errors)
            skills = member.get("skills")
            if (
                not isinstance(skills, list)
                or len(skills) < 2
                or any(not isinstance(skill, str) or not skill.strip() for skill in skills)
            ):
                errors.append(f"team.members[{index}].skills requires at least two values")
            _required_text(member.get("evidence"), f"team.members[{index}].evidence", errors)
            _required_text(
                member.get("prototype_contribution"),
                f"team.members[{index}].prototype_contribution",
                errors,
            )
            _required_text(
                member.get("finalist_contribution"),
                f"team.members[{index}].finalist_contribution",
                errors,
            )

    submission = _mapping(metadata.get("submission"), "submission", errors)
    demo_url = _required_text(submission.get("demo_url"), "submission.demo_url", errors)
    if demo_url and not _public_http_url(demo_url):
        errors.append("submission.demo_url must be a public HTTP(S) URL")
    repository_url = _required_text(
        submission.get("repository_url"), "submission.repository_url", errors
    )
    if repository_url and not _public_http_url(repository_url):
        errors.append("submission.repository_url must be a public HTTP(S) URL")
    recorded_commit = _required_text(
        submission.get("repository_commit"), "submission.repository_commit", errors
    )
    if recorded_commit:
        if not COMMIT_RE.fullmatch(recorded_commit):
            errors.append("submission.repository_commit must be a full lowercase commit")
        elif not _commit_exists(recorded_commit, repository_root):
            errors.append("submission.repository_commit must exist in this repository")
        elif not _commit_is_ancestor(recorded_commit, packaging_commit, repository_root):
            errors.append(
                "submission.repository_commit must be an ancestor of the packaging commit"
            )
    tag = _required_text(submission.get("proposal_tag"), "submission.proposal_tag", errors)
    if tag and not _valid_tag_name(tag):
        errors.append("submission.proposal_tag has an invalid Git tag name")
    elif tag and require_tag and not _tag_points_to_commit(tag, packaging_commit):
        errors.append("submission.proposal_tag must exist and point to the packaging commit")
    for key in ("portal_page_limit", "portal_file_size_limit_mb"):
        value = submission.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            errors.append(f"submission.{key} must be a positive number")
    if not isinstance(submission.get("portal_links_allowed"), bool):
        errors.append("submission.portal_links_allowed must be confirmed true or false")
    if submission.get("portal_dataset_terms_reviewed") is not True:
        errors.append("submission.portal_dataset_terms_reviewed must be true")
    if metadata.get("blocking_fields") != []:
        errors.append("blocking_fields must be an empty array after owner review")
    return errors


def test_receipt_errors(receipt: Mapping[str, Any], tested_commit: str) -> list[str]:
    """Require an all-green receipt bound to the tested source commit."""

    errors: list[str] = []
    if receipt.get("verification_status") != "passed":
        errors.append("test receipt verification_status must be 'passed'")
    if receipt.get("git_commit") != tested_commit:
        errors.append("test receipt git_commit must equal the tested source commit")
    if not _timestamp(receipt.get("generated_at")):
        errors.append("test receipt generated_at must be an offset-aware timestamp")
    suites = receipt.get("suites")
    if not isinstance(suites, list) or not suites:
        errors.append("test receipt must list suites")
    else:
        names: set[str] = set()
        for index, suite in enumerate(suites):
            if not isinstance(suite, Mapping):
                errors.append(f"test suite {index} must be an object")
                continue
            name = suite.get("name")
            if not isinstance(name, str) or not name.strip():
                errors.append(f"test suite {index} requires a name")
                continue
            if name in names:
                errors.append(f"duplicate test suite: {name}")
            names.add(name)
            if suite.get("result") != "passed":
                errors.append(f"test suite {name} is not passed")
            passed = suite.get("passed")
            skipped = suite.get("skipped")
            if not isinstance(passed, int) or isinstance(passed, bool) or passed < 1:
                errors.append(f"test suite {name} requires passed >= 1")
            if not isinstance(skipped, int) or isinstance(skipped, bool) or skipped < 0:
                errors.append(f"test suite {name} has invalid skipped count")
            if suite.get("source_commit") != tested_commit:
                errors.append(f"test suite {name} source_commit must equal tested commit")
            if not isinstance(suite.get("junit_sha256"), str) or not SHA256_RE.fullmatch(
                suite["junit_sha256"]
            ):
                errors.append(f"test suite {name} requires a JUnit SHA-256")
    return errors


def evidence_errors(
    manifest: Mapping[str, Any], tested_commit: str, repository_root: Path = REPOSITORY_ROOT
) -> list[str]:
    """Validate release-critical proposal evidence without optional dependencies."""

    errors: list[str] = []
    if manifest.get("git_commit") != tested_commit:
        errors.append("proposal evidence git_commit must equal the tested source commit")
    if manifest.get("dataset_mode") not in {"fixture_demo", "candidate"}:
        errors.append("proposal evidence must remain fixture_demo or candidate")
    if manifest.get("operational_status") != "non_operational":
        errors.append("proposal evidence must remain non_operational")
    if not _timestamp(manifest.get("generated_at")):
        errors.append("proposal evidence generated_at must be an offset-aware timestamp")
    suites = manifest.get("test_suites")
    if not isinstance(suites, list) or not suites:
        errors.append("proposal evidence must list test suites")
    else:
        for suite in suites:
            if not isinstance(suite, Mapping) or suite.get("result") != "passed":
                name = suite.get("name", "unknown") if isinstance(suite, Mapping) else "unknown"
                errors.append(f"proposal evidence suite is not passed: {name}")

    proof = manifest.get("geoai_proof")
    if not isinstance(proof, Mapping):
        errors.append("proposal evidence requires geoai_proof")
    else:
        if proof.get("can_feed_decision_layer") is not False:
            errors.append("candidate GeoAI proof must not feed the decision layer")
        if proof.get("aggregation_status") != "report_only":
            errors.append("candidate GeoAI aggregation must remain report_only")
        if proof.get("validation_status") != "passed":
            errors.append("GeoAI synthetic validation must be passed")
        if not isinstance(proof.get("reason_blocked"), str) or not proof["reason_blocked"].strip():
            errors.append("blocked GeoAI proof requires reason_blocked")
        for key in ("input_manifest_sha256", "output_probability_sha256"):
            if not isinstance(proof.get(key), str) or not SHA256_RE.fullmatch(proof[key]):
                errors.append(f"geoai_proof.{key} must be a SHA-256 digest")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("proposal evidence must list artifacts")
    else:
        for artifact in artifacts:
            if not isinstance(artifact, Mapping):
                errors.append("proposal evidence artifact must be an object")
                continue
            relative = artifact.get("relative_path")
            digest = artifact.get("sha256")
            if not isinstance(relative, str) or not _safe_relative_path(relative):
                errors.append("proposal evidence contains an unsafe artifact path")
                continue
            path = (repository_root / Path(*Path(relative).parts)).resolve()
            try:
                path.relative_to(repository_root.resolve())
            except ValueError:
                errors.append(f"artifact escapes repository: {relative}")
                continue
            if not path.is_file():
                errors.append(f"artifact is missing: {relative}")
            elif not isinstance(digest, str) or _sha256(path) != digest:
                errors.append(f"artifact checksum is stale: {relative}")
    serialized = json.dumps(manifest, ensure_ascii=False)
    if PRIVATE_PATH_RE.search(serialized):
        errors.append("proposal evidence contains a private absolute path")
    return errors


def final_release_artifact_errors(
    manifest: Mapping[str, Any],
    *,
    require_clean_worktree: bool,
    repository_root: Path = REPOSITORY_ROOT,
) -> list[str]:
    """Require source-derived final documents and a page-inspection receipt."""

    errors: list[str] = []
    required = {
        "final_proposal_docx": FINAL_DOCX_PATH,
        "final_proposal_pdf": FINAL_PDF_PATH,
        "final_pdf_inspection_receipt": FINAL_PDF_INSPECTION_PATH,
    }
    artifacts = manifest.get("artifacts")
    by_kind = {
        artifact.get("kind"): artifact
        for artifact in artifacts
        if isinstance(artifacts, list) and isinstance(artifact, Mapping)
    } if isinstance(artifacts, list) else {}

    for kind, path in required.items():
        if not path.is_file():
            errors.append(f"final release artifact is missing: {path.name}")
        artifact = by_kind.get(kind)
        if not isinstance(artifact, Mapping):
            errors.append(f"proposal evidence is missing artifact kind: {kind}")
            continue
        try:
            expected = path.resolve().relative_to(repository_root.resolve()).as_posix()
        except ValueError:
            errors.append(f"final release artifact escapes repository: {path.name}")
            continue
        if artifact.get("relative_path") != expected:
            errors.append(f"proposal evidence {kind} path must be {expected}")

    if FINAL_DOCX_PATH.is_file():
        if SOURCE_DOCX_PATH.is_file() and _sha256(FINAL_DOCX_PATH) == _sha256(SOURCE_DOCX_PATH):
            errors.append("final proposal DOCX must not be the unchanged retained template")
        try:
            with zipfile.ZipFile(FINAL_DOCX_PATH) as archive:
                document_xml = archive.read("word/document.xml").decode("utf-8", errors="replace")
        except (OSError, KeyError, zipfile.BadZipFile) as exc:
            errors.append(f"final proposal DOCX cannot be inspected: {exc}")
        else:
            if LEGACY_PLACEHOLDER_RE.search(document_xml) or MUSTACHE_RE.search(document_xml):
                errors.append("final proposal DOCX contains an owner placeholder")
            if "DRAFT - RELEASE BLOCKED" in document_xml:
                errors.append("final proposal DOCX contains the draft watermark")
            if PRIVATE_PATH_RE.search(document_xml):
                errors.append("final proposal DOCX contains a private absolute path")

    if (
        FINAL_PDF_PATH.is_file()
        and SOURCE_PDF_PATH.is_file()
        and _sha256(FINAL_PDF_PATH) == _sha256(SOURCE_PDF_PATH)
    ):
        errors.append("final proposal PDF must not be the unchanged retained reference")

    if FINAL_PDF_INSPECTION_PATH.is_file():
        try:
            inspection = load_json(FINAL_PDF_INSPECTION_PATH)
        except SubmissionBuildError as exc:
            errors.append(str(exc))
        else:
            if inspection.get("schema_version") != "1.0":
                errors.append("final PDF inspection schema_version must be '1.0'")
            if not _timestamp(inspection.get("inspected_at")):
                errors.append("final PDF inspection requires an offset-aware inspected_at")
            if not isinstance(inspection.get("reviewer"), str) or not inspection["reviewer"].strip():
                errors.append("final PDF inspection requires a reviewer")
            page_count = inspection.get("page_count")
            if not isinstance(page_count, int) or isinstance(page_count, bool) or page_count < 1:
                errors.append("final PDF inspection requires page_count >= 1")
            checks = (
                "all_pages_visually_inspected",
                "placeholder_scan_passed",
                "private_path_scan_passed",
                "claim_scan_passed",
                "links_checked",
                "source_derived_from_retained_docx",
            )
            for check in checks:
                if inspection.get(check) is not True:
                    errors.append(f"final PDF inspection requires {check}=true")
            if FINAL_DOCX_PATH.is_file() and inspection.get("docx_sha256") != _sha256(
                FINAL_DOCX_PATH
            ):
                errors.append("final PDF inspection DOCX checksum is stale")
            if FINAL_PDF_PATH.is_file() and inspection.get("pdf_sha256") != _sha256(
                FINAL_PDF_PATH
            ):
                errors.append("final PDF inspection PDF checksum is stale")

    if require_clean_worktree and not _worktree_is_clean(repository_root):
        errors.append("post-tag submission check requires a clean worktree")
    return errors


def render_submission_markdown(metadata: Mapping[str, Any], *, draft: bool) -> str:
    """Assemble a reviewable Markdown proposal with generated cover/roster."""

    team = metadata.get("team") if isinstance(metadata.get("team"), Mapping) else {}
    submission = (
        metadata.get("submission") if isinstance(metadata.get("submission"), Mapping) else {}
    )
    if draft:
        team_name = "Submission metadata required"
        institution = "Submission metadata required"
        demo_url = "Not deployed"
        status = "DRAFT - RELEASE BLOCKED"
    else:
        team_name = str(team["name"])
        institution = str(team["institution"])
        demo_url = str(submission["demo_url"])
        status = "Submission release candidate"

    source = PROPOSAL_PATH.read_text(encoding="utf-8")
    section_start = source.find("\n## 1. Problem clarity and Thai relevance")
    if section_start < 0:
        raise SubmissionBuildError("Proposal source is missing its first numbered section.")
    body = source[section_start + 1 :].strip()
    cover = f"""# FloodGuard Thailand

## From Flood Pixels to Equitable Local Action

| Submission field | Value |
|---|---|
| Competition | GeoHackathon 2026 project proposal |
| Team | {team_name} |
| Institution | {institution} |
| Demonstration | Mae Sai 2024 candidate/planning evidence |
| Future transfer | Hat Yai / Songkhla |
| Demo | {demo_url} |
| Status | {status} |

> Thailand can already see floodwater from space. FloodGuard addresses the next
> decision: who may become cut off from help, whether access loss is unequal,
> and where limited preparedness resources should be checked first.

FloodGuard is non-operational and is not an official warning system, guaranteed
real-time detector, or live evacuation navigator.
"""
    roster = _render_roster(team, draft=draft)
    rendered = cover.strip() + "\n\n" + body + "\n\n" + roster + "\n"
    assert_no_release_placeholders(rendered)
    return rendered


def assert_no_release_placeholders(text: str) -> None:
    """Reject legacy owner placeholders from a rendered artifact."""

    if LEGACY_PLACEHOLDER_RE.search(text) or MUSTACHE_RE.search(text):
        raise SubmissionBuildError("Rendered proposal still contains a release placeholder.")


def markdown_to_html(markdown: str, *, draft: bool) -> str:
    """Render the deliberately small Markdown subset used by the proposal."""

    lines = markdown.splitlines()
    output: list[str] = []
    index = 0
    list_type: str | None = None
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            output.append(f"<p>{_inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def close_list() -> None:
        nonlocal list_type
        if list_type:
            output.append(f"</{list_type}>")
            list_type = None

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_paragraph()
            close_list()
            language = stripped[3:].strip()
            code: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code.append(lines[index])
                index += 1
            output.append(
                f'<pre data-language="{html.escape(language)}"><code>'
                + html.escape("\n".join(code))
                + "</code></pre>"
            )
        elif _table_start(lines, index):
            flush_paragraph()
            close_list()
            headers = _table_cells(lines[index])
            index += 2
            rows: list[list[str]] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append(_table_cells(lines[index]))
                index += 1
            index -= 1
            output.append("<table><thead><tr>")
            output.extend(f"<th>{_inline(value)}</th>" for value in headers)
            output.append("</tr></thead><tbody>")
            for row in rows:
                output.append("<tr>")
                padded = row + [""] * max(0, len(headers) - len(row))
                output.extend(f"<td>{_inline(value)}</td>" for value in padded[: len(headers)])
                output.append("</tr>")
            output.append("</tbody></table>")
        elif not stripped:
            flush_paragraph()
            close_list()
        elif match := re.match(r"^(#{1,6})\s+(.+)$", stripped):
            flush_paragraph()
            close_list()
            level = len(match.group(1))
            output.append(f"<h{level}>{_inline(match.group(2))}</h{level}>")
        elif stripped.startswith("> "):
            flush_paragraph()
            close_list()
            quote = [stripped[2:].strip()]
            while index + 1 < len(lines) and lines[index + 1].strip().startswith("> "):
                index += 1
                quote.append(lines[index].strip()[2:].strip())
            output.append(f"<blockquote>{_inline(' '.join(quote))}</blockquote>")
        elif match := re.match(r"^[-*]\s+(.+)$", stripped):
            flush_paragraph()
            if list_type != "ul":
                close_list()
                output.append("<ul>")
                list_type = "ul"
            output.append(f"<li>{_inline(match.group(1))}</li>")
        elif match := re.match(r"^\d+\.\s+(.+)$", stripped):
            flush_paragraph()
            if list_type != "ol":
                close_list()
                output.append("<ol>")
                list_type = "ol"
            output.append(f"<li>{_inline(match.group(1))}</li>")
        else:
            if list_type and output and output[-1].endswith("</li>"):
                output[-1] = output[-1][:-5] + " " + _inline(stripped) + "</li>"
            else:
                paragraph.append(stripped)
        index += 1
    flush_paragraph()
    close_list()
    watermark = '<div class="watermark">DRAFT - RELEASE BLOCKED</div>' if draft else ""
    return _html_document("\n".join(output), watermark=watermark)


def build(
    *,
    draft: bool,
    output_dir: Path,
    emit_pdf: bool,
    check_only: bool = False,
    pre_tag: bool = False,
) -> list[Path]:
    """Validate inputs and optionally create a preliminary draft preview.

    Final PDF layout must be derived from the retained polished DOCX. The
    built-in HTML renderer exists only for visibly watermarked draft review.
    """

    if emit_pdf and not draft:
        raise SubmissionBuildError(
            "Final PDF must be rendered from a copy of the retained polished DOCX; "
            "the HTML/PDF renderer is draft-only."
        )

    if pre_tag and (draft or not check_only):
        raise SubmissionBuildError("pre-tag validation requires --check without --draft")

    packaging_commit = current_commit()
    metadata = load_json(METADATA_PATH)
    if not draft:
        errors = metadata_errors(
            metadata,
            packaging_commit,
            require_tag=not pre_tag,
        )
        submission = (
            metadata.get("submission")
            if isinstance(metadata.get("submission"), Mapping)
            else {}
        )
        tested_commit = submission.get("repository_commit")
        if not isinstance(tested_commit, str) or not COMMIT_RE.fullmatch(tested_commit):
            tested_commit = ""
        receipt = load_json(TEST_RECEIPT_PATH)
        errors.extend(test_receipt_errors(receipt, tested_commit))
        if not EVIDENCE_PATH.is_file():
            errors.append("final proposal evidence manifest is missing")
        else:
            manifest = load_json(EVIDENCE_PATH)
            errors.extend(evidence_errors(manifest, tested_commit))
            errors.extend(
                final_release_artifact_errors(
                    manifest,
                    require_clean_worktree=not pre_tag,
                )
            )
        if errors:
            raise SubmissionBuildError("\n- " + "\n- ".join(sorted(set(errors))))

    rendered = render_submission_markdown(metadata, draft=draft)
    rendered_html = markdown_to_html(rendered, draft=draft)
    assert_no_release_placeholders(rendered_html)
    if check_only:
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = FINAL_STEM + ("_DRAFT" if draft else "")
    markdown_path = output_dir / f"{stem}.md"
    html_path = output_dir / f"{stem}.html"
    markdown_path.write_text(rendered, encoding="utf-8", newline="\n")
    html_path.write_text(rendered_html, encoding="utf-8", newline="\n")
    outputs = [markdown_path, html_path]
    if emit_pdf:
        pdf_path = output_dir / f"{stem}.pdf"
        _print_pdf(html_path, pdf_path)
        outputs.append(pdf_path)
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", action="store_true", help="Build a watermarked blocked draft.")
    parser.add_argument("--check", action="store_true", help="Validate without writing outputs.")
    parser.add_argument(
        "--pre-tag",
        action="store_true",
        help=(
            "Run the strict source/evidence check before the packaging commit is tagged; "
            "requires --check and does not declare the release complete."
        ),
    )
    parser.add_argument(
        "--pdf",
        action="store_true",
        help="Print a watermarked draft HTML preview to PDF; requires --draft.",
    )
    parser.add_argument("--output-dir", type=Path, default=PACKAGE_ROOT / "dist")
    args = parser.parse_args(argv)
    try:
        outputs = build(
            draft=args.draft,
            output_dir=args.output_dir,
            emit_pdf=args.pdf,
            check_only=args.check,
            pre_tag=args.pre_tag,
        )
    except (SubmissionBuildError, subprocess.CalledProcessError) as exc:
        print(f"SUBMISSION BLOCKED: {exc}", file=sys.stderr)
        return 2
    for output in outputs:
        print(output)
    if args.check:
        if args.pre_tag:
            print("Pre-tag package check passed; post-tag verification is still required.")
        else:
            print("Submission package check passed.")
    return 0


def _mapping(value: Any, label: str, errors: list[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        errors.append(f"{label} must be an object")
        return {}
    return value


def _required_text(value: Any, label: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label} is required")
        return None
    return value.strip()


def _public_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc) and not parsed.username


def _tag_points_to_commit(tag: str, commit: str) -> bool:
    if not _valid_tag_name(tag):
        return False
    completed = subprocess.run(
        ["git", "rev-parse", f"{tag}^{{commit}}"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0 and completed.stdout.strip().lower() == commit


def _valid_tag_name(tag: str) -> bool:
    """Accept the intentionally narrow tag form used by the release package."""

    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}", tag))


def _commit_exists(commit: str, repository_root: Path = REPOSITORY_ROOT) -> bool:
    """Return whether a full commit hash resolves in the local repository."""

    completed = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


def _commit_is_ancestor(
    tested_commit: str,
    packaging_commit: str,
    repository_root: Path = REPOSITORY_ROOT,
) -> bool:
    """Return whether the tested source is contained by the packaging commit."""

    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", tested_commit, packaging_commit],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


def _worktree_is_clean(repository_root: Path = REPOSITORY_ROOT) -> bool:
    """Return whether tracked and untracked release-relevant files are clean."""

    completed = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0 and not completed.stdout.strip()


def _timestamp(value: Any) -> bool:
    if not isinstance(value, str) or "T" not in value:
        return False
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative_path(value: str) -> bool:
    return (
        not PRIVATE_PATH_RE.search(value)
        and "\\" not in value
        and not value.startswith("/")
        and ".." not in Path(value).parts
    )


def _render_roster(team: Mapping[str, Any], *, draft: bool) -> str:
    lines = ["## Team capability and evidence", ""]
    members = team.get("members") if isinstance(team.get("members"), list) else []
    if draft:
        lines.append(
            "Owner-supplied identities, skills and evidence are required before release. "
            "The planned roles are listed below without fabricated personal details."
        )
        lines.append("")
    for index, raw in enumerate(members, start=1):
        member = raw if isinstance(raw, Mapping) else {}
        name = (
            "Owner-supplied identity required"
            if draft
            else str(member.get("full_name", "")).strip()
        )
        lines.extend(
            [
                f"### Member {index}: {name}",
                "",
                f"**Role:** {member.get('role', '')}",
                "",
            ]
        )
        if not draft:
            skills = ", ".join(str(item) for item in member.get("skills", []))
            lines.extend(
                [
                    f"**Relevant skills:** {skills}",
                    "",
                    f"**Evidence:** {member.get('evidence', '')}",
                    "",
                ]
            )
        lines.extend(
            [
                f"**Proposal-stage contribution:** {member.get('prototype_contribution', '')}",
                "",
                f"**Finalist-stage contribution:** {member.get('finalist_contribution', '')}",
                "",
            ]
        )
    return "\n".join(lines).strip()


def _table_start(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines) or not lines[index].strip().startswith("|"):
        return False
    separator = lines[index + 1].strip()
    return bool(
        separator.startswith("|")
        and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in _table_cells(separator))
    )


def _table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _inline(value: str) -> str:
    escaped = html.escape(value, quote=True)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(
        r"\[([^\]]+)\]\((https?://[^)]+)\)",
        r'<a href="\2">\1</a>',
        escaped,
    )
    return escaped


def _html_document(body: str, *, watermark: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FloodGuard Thailand - GeoHackathon 2026 Proposal</title>
<style>
  @page {{ size: A4; margin: 17mm 18mm 18mm; }}
  :root {{ --navy:#0b2b4f; --teal:#0c9a92; --ink:#203246; --muted:#61758d; --line:#d8e5eb; --soft:#eef7f6; --rose:#b33b52; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0 auto; max-width:980px; color:var(--ink); background:white; font:11.2pt/1.48 "Noto Sans Thai","Leelawadee UI","Segoe UI",Arial,sans-serif; }}
  h1,h2,h3 {{ color:var(--navy); break-after:avoid; }}
  h1 {{ font:700 30pt/1.1 Georgia,serif; margin:0 0 8mm; padding:13mm 11mm; color:white; background:var(--navy); }}
  h2 {{ font:700 20pt/1.18 Georgia,serif; margin:10mm 0 4mm; border-bottom:1px solid var(--line); padding-bottom:2mm; }}
  h3 {{ font-size:14pt; color:var(--teal); margin:7mm 0 2mm; }}
  p {{ margin:0 0 3.4mm; orphans:3; widows:3; }}
  blockquote {{ margin:5mm 0; padding:4mm 5mm; border-left:4px solid var(--teal); background:var(--soft); font-size:11.5pt; }}
  ul,ol {{ margin:2mm 0 4mm 7mm; padding-left:5mm; break-inside:avoid; }}
  li {{ margin:1mm 0; }}
  code {{ color:#0a5370; font:9.5pt Consolas,monospace; }}
  pre {{ padding:4mm; overflow-wrap:anywhere; white-space:pre-wrap; border:1px solid var(--line); border-radius:3mm; background:#f6f9fb; break-inside:avoid; }}
  table {{ width:100%; border-collapse:collapse; margin:4mm 0 6mm; font-size:9.4pt; break-inside:auto; }}
  thead {{ display:table-header-group; }}
  tr {{ break-inside:avoid; }}
  th {{ color:white; background:var(--navy); text-align:left; }}
  th,td {{ border:1px solid var(--line); padding:2.4mm 2.7mm; vertical-align:top; }}
  tbody tr:nth-child(even) {{ background:#f6f9fb; }}
  a {{ color:#087a82; text-decoration:none; }}
  .watermark {{ position:fixed; top:44%; left:7%; transform:rotate(-28deg); z-index:999; color:rgba(179,59,82,.11); font:700 42pt Arial,sans-serif; letter-spacing:2px; pointer-events:none; }}
  @media screen {{ body {{ padding:24px; box-shadow:0 0 30px rgba(11,43,79,.12); }} }}
</style>
</head>
<body>
{watermark}
{body}
</body>
</html>
"""


def _print_pdf(html_path: Path, pdf_path: Path) -> None:
    chrome = _find_chrome()
    with tempfile.TemporaryDirectory(prefix="floodguard-proposal-chrome-") as profile:
        subprocess.run(
            [
                str(chrome),
                "--headless=new",
                "--disable-gpu",
                "--no-first-run",
                "--no-default-browser-check",
                f"--user-data-dir={profile}",
                "--no-pdf-header-footer",
                f"--print-to-pdf={pdf_path.resolve()}",
                html_path.resolve().as_uri(),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    if not pdf_path.is_file() or pdf_path.stat().st_size < 10_000:
        raise SubmissionBuildError("Chrome did not create a non-empty proposal PDF.")


def _find_chrome() -> Path:
    candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    ]
    discovered = shutil.which("chrome") or shutil.which("google-chrome")
    if discovered:
        candidates.insert(0, Path(discovered))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise SubmissionBuildError("Local Chrome is required for reproducible PDF printing.")


if __name__ == "__main__":
    raise SystemExit(main())
