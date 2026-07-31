"""Offline, practice-only Reviewer A workspace for synthetic SAR exercises.

The workspace generated here is deliberately separated from the formal label
factory.  It consumes only the deterministic synthetic learning package, never
opens real event queries, and emits practice downloads whose schemas cannot be
mistaken for formal reviewer annotations.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import struct
import tempfile
from typing import Any, Mapping
import zlib

from floodguard.label_factory.synthetic_learning import (
    SYNTHETIC_LEARNING_SCHEMA,
    SyntheticLearningError,
    verify_synthetic_learning_package,
)
from floodguard.label_factory.synthetic_remediation import (
    SYNTHETIC_REMEDIATION_SCHEMA,
    SyntheticRemediationError,
    verify_synthetic_remediation_package,
)


WORKSPACE_SCHEMA = "floodguard.reviewer_practice_workspace.v1"
PRACTICE_DATA_SCHEMA = "floodguard.reviewer_practice_workspace_data.v1"
PRACTICE_ANSWER_SCHEMA = "floodguard.reviewer_practice_answer.v1"
CASE_ID_PATTERN = re.compile(r"(?:SYN-SAR|SYN-REM)-[0-9]{3}")
SUPPORTED_SOURCE_SCHEMAS = frozenset(
    (SYNTHETIC_LEARNING_SCHEMA, SYNTHETIC_REMEDIATION_SCHEMA)
)
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
PANEL_FILES: tuple[str, ...] = (
    "pre_vv.png",
    "event_vv.png",
    "pre_vh.png",
    "event_vh.png",
    "vv_change.png",
    "permanent_water.png",
    "slope.png",
    "landcover.png",
)
PANEL_LABELS: Mapping[str, str] = {
    "pre_vv.png": "Pre VV",
    "event_vv.png": "Event VV",
    "pre_vh.png": "Pre VH",
    "event_vh.png": "Event VH",
    "vv_change.png": "VV change (pre - event)",
    "permanent_water.png": "Permanent water",
    "slope.png": "Slope",
    "landcover.png": "Land cover",
}
LABEL_RGB_TO_CODE: Mapping[tuple[int, int, int], int] = {
    (120, 120, 120): 0,
    (35, 113, 210): 1,
    (55, 205, 218): 2,
    (245, 194, 66): 3,
    (202, 67, 196): 4,
    (0, 0, 0): 255,
}
SAFETY_FLAGS: Mapping[str, bool] = {
    "practice_only": True,
    "conceptual_teaching_only": True,
    "formal_review_authorized": False,
    "formal_reviewer_calibration": False,
    "real_event_queries_used": False,
    "eligible_for_reviewer_calibration": False,
    "eligible_for_agreement": False,
    "eligible_for_consensus": False,
    "eligible_for_query_model_training": False,
    "eligible_for_model_evaluation": False,
    "eligible_for_decision_layer": False,
    "eligible_for_fpps": False,
    "eligible_for_warning": False,
}


class ReviewerWorkspaceError(ValueError):
    """Raised when a safe practice workspace cannot be created."""


def build_reviewer_practice_workspace(
    source_directory: str | Path,
    output_directory: str | Path,
    reviewer_display_name: str,
    created_at_utc: datetime,
    formal_hold_path: str | Path | None = None,
) -> Path:
    """Build a write-once, offline Reviewer A practice workspace.

    The returned path is the output directory.  The output contains only
    synthetic learning images, a browser workbench, and a checksum manifest.
    It contains no formal annotation template, real query metadata, weak label,
    model score, selection rank, or decision-layer artifact.
    """

    source = Path(source_directory).resolve()
    target = Path(output_directory).resolve()
    reviewer = _reviewer_name(reviewer_display_name)
    created = _utc_timestamp(created_at_utc)
    _validate_output_location(source, target)

    source_manifest_path = source / "manifest.json"
    source_manifest = _read_json_object(source_manifest_path, "synthetic manifest")
    source_schema = source_manifest.get("artifact_schema")
    if source_schema == SYNTHETIC_LEARNING_SCHEMA:
        verifier = verify_synthetic_learning_package
    elif source_schema == SYNTHETIC_REMEDIATION_SCHEMA:
        verifier = verify_synthetic_remediation_package
    else:
        raise ReviewerWorkspaceError("Unsupported synthetic learning manifest schema.")
    try:
        verifier(source)
    except (
        SyntheticLearningError,
        SyntheticRemediationError,
        OSError,
        ValueError,
    ) as exc:
        raise ReviewerWorkspaceError(
            f"Synthetic learning package checksum verification failed: {exc}"
        ) from exc

    cases = _sanitize_source_cases(source_manifest)
    hold = _read_formal_hold(formal_hold_path)

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{target.name}.tmp-", dir=target.parent)
    )
    try:
        artifact_hashes: dict[str, str] = {}
        learner_cases: list[dict[str, Any]] = []
        for case in cases:
            case_id = case["case_id"]
            case_assets = temporary / "assets" / "cases" / case_id
            case_assets.mkdir(parents=True)
            panel_rows: list[dict[str, str]] = []
            declared_panels = case["panel_sha256"]
            for panel_name in PANEL_FILES:
                source_panel = source / case_id / panel_name
                destination = case_assets / panel_name
                expected_sha = _required_sha(
                    declared_panels.get(panel_name),
                    f"{case_id} {panel_name}",
                )
                _copy_verified(source_panel, destination, expected_sha)
                relative = destination.relative_to(temporary).as_posix()
                artifact_hashes[relative] = expected_sha
                panel_rows.append(
                    {
                        "id": panel_name.removesuffix(".png"),
                        "label": PANEL_LABELS[panel_name],
                        "path": relative,
                    }
                )

            answer_name = f"{case_id}_labels.png"
            source_answer = source / "answer_key" / answer_name
            answer_destination = temporary / "assets" / "reveal" / answer_name
            answer_destination.parent.mkdir(parents=True, exist_ok=True)
            expected_answer_sha = _required_sha(
                case.get("answer_label_sha256"), f"{case_id} answer mask"
            )
            _copy_verified(source_answer, answer_destination, expected_answer_sha)
            answer_relative = answer_destination.relative_to(temporary).as_posix()
            artifact_hashes[answer_relative] = expected_answer_sha

            answer_codes = _read_label_codes(source_answer)
            answer_script = temporary / "assets" / "reveal" / f"{case_id}_answer.js"
            answer_payload = {
                "artifact_schema": PRACTICE_ANSWER_SCHEMA,
                "caseId": case_id,
                "answerPath": answer_relative,
                "codes": answer_codes,
                "teachingChallenge": str(case.get("challenge", "")),
                "expectedPrimary": str(case.get("expected_primary", "")),
                "teachingRationale": str(case.get("rationale", "")),
                "teachingReasons": _safe_text_list(
                    case.get("ambiguity_tags", []), f"{case_id} teaching reasons"
                ),
            }
            answer_script.write_text(
                "window.FloodGuardPracticeAnswers = "
                "window.FloodGuardPracticeAnswers || {};\n"
                f"window.FloodGuardPracticeAnswers[{json.dumps(case_id)}] = "
                f"{_json_for_script(answer_payload)};\n",
                encoding="utf-8",
            )
            answer_script_relative = answer_script.relative_to(temporary).as_posix()
            artifact_hashes[answer_script_relative] = _sha256(answer_script)

            learner_cases.append(
                {
                    "caseId": case_id,
                    "panels": panel_rows,
                    "revealScript": answer_script_relative,
                }
            )

        workspace_seed = {
            "source_manifest_sha256": _sha256(source_manifest_path),
            "reviewer_display_name": reviewer,
            "created_at_utc": created,
            "case_ids": [row["caseId"] for row in learner_cases],
        }
        workspace_id = "FG-PRACTICE-" + _canonical_hash(workspace_seed)[:16].upper()
        learner_data = {
            "artifact_schema": PRACTICE_DATA_SCHEMA,
            "workspaceId": workspace_id,
            "reviewerDisplayName": reviewer,
            "createdAtUtc": created,
            "practiceOnly": True,
            "conceptualTeachingOnly": True,
            "formalHold": {
                "evidenceSupplied": hold["evidence_supplied"],
                "active": hold["formal_hold_active"],
                "status": hold["status"],
                "reason": hold["reason"],
            },
            "cases": learner_cases,
        }
        data_path = temporary / "workspace_data.js"
        data_path.write_text(
            "window.FloodGuardPracticeWorkspace = "
            f"{_json_for_script(learner_data)};\n",
            encoding="utf-8",
        )

        index_path = temporary / "index.html"
        index_path.write_text(
            _INDEX_HTML.replace("{{REVIEWER_NAME}}", html.escape(reviewer)),
            encoding="utf-8",
        )
        styles_path = temporary / "styles.css"
        styles_path.write_text(_STYLES_CSS, encoding="utf-8")
        app_path = temporary / "app.js"
        app_path.write_text(_APP_JS, encoding="utf-8")
        readme_path = temporary / "README.md"
        readme_path.write_text(
            _readme_text(reviewer=reviewer, created=created, hold=hold),
            encoding="utf-8",
        )
        for path in (data_path, index_path, styles_path, app_path, readme_path):
            artifact_hashes[path.relative_to(temporary).as_posix()] = _sha256(path)

        if formal_hold_path is not None:
            hold_source = Path(formal_hold_path).resolve()
            hold_copy = temporary / "governance" / "FORMAL_REVIEW_HOLD.json"
            hold_copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(hold_source, hold_copy)
            if _sha256(hold_copy) != hold["source_file_sha256"]:
                raise ReviewerWorkspaceError(
                    "Formal hold changed while the workspace was being created."
                )
            artifact_hashes[hold_copy.relative_to(temporary).as_posix()] = hold[
                "source_file_sha256"
            ]

        manifest_unsigned: dict[str, Any] = {
            "artifact_schema": WORKSPACE_SCHEMA,
            "workspace_id": workspace_id,
            "created_at_utc": created,
            "reviewer_display_name": reviewer,
            "case_count": len(learner_cases),
            "case_ids": [row["caseId"] for row in learner_cases],
            "source_package": {
                "artifact_schema": source_manifest.get("artifact_schema"),
                "manifest_file_sha256": _sha256(source_manifest_path),
                "manifest_self_sha256": _required_sha(
                    source_manifest.get("manifest_sha256"),
                    "source manifest self hash",
                ),
                "generator_version": str(source_manifest.get("generator_version", "")),
            },
            "formal_hold": hold,
            "safety": {
                **SAFETY_FLAGS,
                "formal_hold_active": hold["formal_hold_active"],
                "practice_exports_only": True,
                "formal_import_schema_emitted": False,
                "answer_release_is_ui_gated_not_cryptographic": True,
            },
            "artifact_sha256": dict(sorted(artifact_hashes.items())),
            "assumptions": (
                "Offline synthetic practice interface. Answer feedback is UI-gated "
                "after an attempt locks, not cryptographically hidden. Practice "
                "downloads are not formal reviewer annotations."
            ),
        }
        manifest_unsigned["manifest_sha256"] = _canonical_hash(manifest_unsigned)
        manifest_path = temporary / "workspace_manifest.json"
        manifest_path.write_text(
            json.dumps(
                manifest_unsigned,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )

        _assert_generated_workspace(temporary, expected_case_count=len(learner_cases))
        if target.exists():
            target.rmdir()
        temporary.rename(target)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return target


def _validate_output_location(source: Path, target: Path) -> None:
    if not source.is_dir():
        raise ReviewerWorkspaceError(f"Synthetic source directory does not exist: {source}")
    if target == source or source in target.parents:
        raise ReviewerWorkspaceError(
            "Output must be outside the synthetic source package."
        )
    if target.exists():
        if not target.is_dir():
            raise FileExistsError(f"Output already exists and is not a directory: {target}")
        if any(target.iterdir()):
            raise FileExistsError(
                f"Output directory must be new or empty; overwrite is forbidden: {target}"
            )


def _sanitize_source_cases(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    if manifest.get("artifact_schema") not in SUPPORTED_SOURCE_SCHEMAS:
        raise ReviewerWorkspaceError("Unsupported synthetic learning manifest schema.")
    for key, expected in {
        "conceptual_teaching_only": True,
        "formal_reviewer_calibration": False,
        "real_event_queries_used": False,
        "eligible_for_query_model_training": False,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }.items():
        if manifest.get(key) is not expected:
            raise ReviewerWorkspaceError(
                f"Synthetic manifest safety field {key} must be {expected}."
            )
    raw_ids = manifest.get("case_ids")
    raw_cases = manifest.get("cases")
    if not isinstance(raw_ids, list) or not isinstance(raw_cases, list):
        raise ReviewerWorkspaceError("Synthetic manifest must contain case_ids and cases lists.")
    case_ids = [_safe_case_id(value) for value in raw_ids]
    if len(case_ids) != len(set(case_ids)) or case_ids != sorted(case_ids):
        raise ReviewerWorkspaceError("Synthetic case ids must be unique and ordered.")
    if int(manifest.get("case_count", -1)) != len(case_ids) or len(case_ids) != len(raw_cases):
        raise ReviewerWorkspaceError("Synthetic case count does not match its case lists.")
    if not case_ids:
        raise ReviewerWorkspaceError("Synthetic package contains no practice cases.")
    by_id: dict[str, dict[str, Any]] = {}
    for raw in raw_cases:
        if not isinstance(raw, dict):
            raise ReviewerWorkspaceError("Synthetic case rows must be JSON objects.")
        case_id = _safe_case_id(raw.get("case_id"))
        if case_id in by_id:
            raise ReviewerWorkspaceError(f"Duplicate synthetic case: {case_id}")
        challenge = str(raw.get("challenge", "")).strip()
        if not challenge or len(challenge) > 240:
            raise ReviewerWorkspaceError(f"Synthetic case {case_id} has invalid challenge text.")
        panels = raw.get("panel_sha256")
        if not isinstance(panels, dict) or set(panels) != set(PANEL_FILES):
            raise ReviewerWorkspaceError(
                f"Synthetic case {case_id} has an incomplete panel checksum set."
            )
        by_id[case_id] = dict(raw)
    if list(by_id) != case_ids:
        raise ReviewerWorkspaceError("Synthetic case row order does not match case_ids.")
    return [by_id[case_id] for case_id in case_ids]


def _read_formal_hold(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "evidence_supplied": False,
            "formal_hold_active": True,
            "status": "hold_evidence_not_supplied",
            "reason": (
                "No formal-hold evidence file was supplied to this practice package. "
                "Formal review remains unavailable from this workspace."
            ),
            "source_file_sha256": None,
        }
    source = Path(path).resolve()
    payload = _read_json_object(source, "formal review hold")
    if payload.get("artifact_schema") != "floodguard.formal_review_hold.v1":
        raise ReviewerWorkspaceError("Unsupported formal review hold schema.")
    if payload.get("hold") is not True:
        raise ReviewerWorkspaceError(
            "The supplied formal review hold must be active for this practice-only workspace."
        )
    reason = str(payload.get("hold_reason", "")).strip()
    if not reason or len(reason) > 2000:
        raise ReviewerWorkspaceError("Formal review hold reason must be bounded non-blank text.")
    return {
        "evidence_supplied": True,
        "formal_hold_active": True,
        "status": "active_read_only_hold",
        "reason": reason,
        "source_file_sha256": _sha256(source),
    }


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ReviewerWorkspaceError(f"{label} does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewerWorkspaceError(f"Could not read {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ReviewerWorkspaceError(f"{label} must be a JSON object.")
    return payload


def _copy_verified(source: Path, destination: Path, expected_sha: str) -> None:
    if not source.is_file() or _sha256(source) != expected_sha:
        raise ReviewerWorkspaceError(
            f"Source checksum verification failed for {source.name}."
        )
    shutil.copyfile(source, destination)
    if _sha256(destination) != expected_sha:
        raise ReviewerWorkspaceError(
            f"Copied checksum verification failed for {source.name}."
        )


def _read_label_codes(path: Path) -> list[int]:
    """Decode the deterministic 32 x 32 RGB answer PNG without image libraries."""

    payload = path.read_bytes()
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ReviewerWorkspaceError(f"Answer mask is not a PNG: {path.name}")
    offset = 8
    width = height = bit_depth = color_type = interlace = None
    compressed = bytearray()
    while offset < len(payload):
        if offset + 12 > len(payload):
            raise ReviewerWorkspaceError(f"Truncated PNG chunk in {path.name}.")
        length = struct.unpack(">I", payload[offset : offset + 4])[0]
        kind = payload[offset + 4 : offset + 8]
        data_start = offset + 8
        data_end = data_start + length
        if data_end + 4 > len(payload):
            raise ReviewerWorkspaceError(f"Truncated PNG data in {path.name}.")
        data = payload[data_start:data_end]
        expected_crc = struct.unpack(">I", payload[data_end : data_end + 4])[0]
        if zlib.crc32(kind + data) & 0xFFFFFFFF != expected_crc:
            raise ReviewerWorkspaceError(f"PNG CRC check failed for {path.name}.")
        if kind == b"IHDR":
            width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(
                ">IIBBBBB", data
            )
            if compression != 0 or filter_method != 0:
                raise ReviewerWorkspaceError(f"Unsupported PNG encoding in {path.name}.")
        elif kind == b"IDAT":
            compressed.extend(data)
        elif kind == b"IEND":
            break
        offset = data_end + 4
    if (width, height, bit_depth, color_type, interlace) != (32, 32, 8, 2, 0):
        raise ReviewerWorkspaceError(
            f"Answer mask must be a non-interlaced 32 x 32 RGB PNG: {path.name}"
        )
    try:
        raw = zlib.decompress(bytes(compressed))
    except zlib.error as exc:
        raise ReviewerWorkspaceError(f"Could not decode answer PNG {path.name}.") from exc
    stride = 32 * 3
    if len(raw) != 32 * (stride + 1):
        raise ReviewerWorkspaceError(f"Answer PNG has unexpected byte length: {path.name}")
    previous = bytearray(stride)
    codes: list[int] = []
    position = 0
    for _row in range(32):
        filter_type = raw[position]
        scanline = bytearray(raw[position + 1 : position + 1 + stride])
        position += stride + 1
        _undo_png_filter(scanline, previous, filter_type, bytes_per_pixel=3)
        for column in range(32):
            rgb = tuple(scanline[column * 3 : column * 3 + 3])
            if rgb not in LABEL_RGB_TO_CODE:
                raise ReviewerWorkspaceError(
                    f"Answer mask {path.name} contains an unknown label colour {rgb}."
                )
            codes.append(LABEL_RGB_TO_CODE[rgb])
        previous = scanline
    return codes


def _undo_png_filter(
    row: bytearray,
    previous: bytearray,
    filter_type: int,
    *,
    bytes_per_pixel: int,
) -> None:
    if filter_type == 0:
        return
    for index in range(len(row)):
        left = row[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
        above = previous[index]
        upper_left = previous[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
        if filter_type == 1:
            predictor = left
        elif filter_type == 2:
            predictor = above
        elif filter_type == 3:
            predictor = (left + above) // 2
        elif filter_type == 4:
            predictor = _paeth(left, above, upper_left)
        else:
            raise ReviewerWorkspaceError(f"Unsupported PNG filter type: {filter_type}")
        row[index] = (row[index] + predictor) & 0xFF


def _paeth(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    distance_left = abs(estimate - left)
    distance_above = abs(estimate - above)
    distance_upper_left = abs(estimate - upper_left)
    if distance_left <= distance_above and distance_left <= distance_upper_left:
        return left
    if distance_above <= distance_upper_left:
        return above
    return upper_left


def _assert_generated_workspace(root: Path, *, expected_case_count: int) -> None:
    required = (
        "index.html",
        "styles.css",
        "app.js",
        "workspace_data.js",
        "README.md",
    )
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise ReviewerWorkspaceError("Generated workspace is incomplete: " + ", ".join(missing))
    png_count = sum(1 for _path in root.rglob("*.png"))
    if png_count != expected_case_count * (len(PANEL_FILES) + 1):
        raise ReviewerWorkspaceError(
            f"Generated workspace has {png_count} PNGs; expected "
            f"{expected_case_count * (len(PANEL_FILES) + 1)}."
        )
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".tif", ".tiff", ".gpkg", ".geojson", ".csv"}:
            raise ReviewerWorkspaceError(f"Forbidden formal-data file in practice workspace: {path.name}")
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".html", ".css", ".js", ".json", ".md"}
    )
    if re.search(r"(?i)\bhttps?://|\bfile://|[a-z]:[\\/]", combined):
        raise ReviewerWorkspaceError("Generated practice workspace contains an external or absolute path.")
    if "fetch(" in combined:
        raise ReviewerWorkspaceError("Generated practice workspace must not use network fetch.")


def _safe_case_id(value: object) -> str:
    text = str(value)
    if CASE_ID_PATTERN.fullmatch(text) is None:
        raise ReviewerWorkspaceError(f"Unsafe synthetic case id: {text!r}")
    return text


def _safe_text_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ReviewerWorkspaceError(f"{label} must be a list.")
    result: list[str] = []
    for item in value:
        text = str(item).strip()
        if not text or len(text) > 120:
            raise ReviewerWorkspaceError(f"{label} contains invalid text.")
        result.append(text)
    return result


def _reviewer_name(value: object) -> str:
    text = str(value).strip()
    if not text or len(text) > 120 or any(ord(character) < 32 for character in text):
        raise ReviewerWorkspaceError(
            "reviewer_display_name must be bounded, non-blank display text."
        )
    return text


def _utc_timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ReviewerWorkspaceError("created_at_utc must be timezone-aware.")
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _required_sha(value: object, label: str) -> str:
    text = str(value).strip().lower()
    if SHA256_PATTERN.fullmatch(text) is None:
        raise ReviewerWorkspaceError(f"{label} must be a complete SHA-256.")
    return text


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _json_for_script(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).replace("</", "<\\/")


def _readme_text(*, reviewer: str, created: str, hold: Mapping[str, Any]) -> str:
    hold_status = "ACTIVE" if hold["formal_hold_active"] else "UNKNOWN"
    return f"""# FloodGuard Reviewer A Practice Workbench

Reviewer display name: {reviewer}
Created UTC: {created}
Formal review hold: {hold_status}

Open `index.html` in a modern browser. All evidence images and application code
are local. No network service, sign-in, or formal event data is used.

This workspace is practice only. It uses deterministic conceptual teaching
images, not physical Sentinel-1 observations. Its downloads use practice-only
schemas and are not accepted by the formal annotation importer. It cannot
authorize calibration, agreement, consensus, model training, model evaluation,
the decision layer, FPPS, or a warning.

The post-lock answer gate is a usability control, not cryptographic blinding.
The answer bytes are packaged locally so the workbench remains offline.
"""


_INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'self' data: blob:; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
  <title>FloodGuard Reviewer A Practice Workbench</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <div class="practice-banner" role="status">PRACTICE ONLY · SYNTHETIC TEACHING CASES · NOT FORMAL REVIEW</div>
  <header class="app-header">
    <div>
      <p class="eyebrow">FloodGuard label factory learning</p>
      <h1>Reviewer A Practice Workbench</h1>
      <p>Reviewer: <strong>{{REVIEWER_NAME}}</strong></p>
    </div>
    <div class="header-badges" aria-label="Workspace safety status">
      <span class="badge practice">Practice-only</span>
      <span class="badge">Offline</span>
      <span class="badge">Conceptual synthetic data</span>
    </div>
  </header>

  <section id="formal-hold-banner" data-testid="formal-hold" class="hold-card" aria-label="Formal review hold">
    <div><strong>Formal review hold</strong><span id="hold-state">Loading immutable hold status…</span></div>
    <p id="hold-reason"></p>
    <p class="safety-line">This read-only gate cannot be changed here. The workspace has no real query access and cannot authorize formal work.</p>
  </section>

  <section class="workflow-strip" aria-label="Human workflow position">
    <div class="workflow-step active"><span>1</span><strong>Practice</strong><small>Available now</small></div>
    <div class="workflow-step held"><span>2</span><strong>Unseen review gate</strong><small>Held</small></div>
    <div class="workflow-step held"><span>3</span><strong>Independent formal review</strong><small>Held</small></div>
    <div class="workflow-step held"><span>4</span><strong>Agreement and consensus</strong><small>Held</small></div>
    <div class="workflow-step held"><span>5</span><strong>Research model</strong><small>Held</small></div>
  </section>

  <main class="workspace">
    <aside class="queue-panel" aria-label="Case navigation">
      <div class="panel-heading">
        <div><p class="eyebrow">Practice queue</p><h2>Cases</h2></div>
        <span id="progress-count" data-testid="progress">0 / 0 locked</span>
      </div>
      <div class="progress-track" aria-hidden="true"><span id="progress-bar"></span></div>
      <div id="case-nav" data-testid="case-nav" class="case-list" role="list"></div>
      <div class="queue-actions" aria-label="Practice export controls">
        <button id="export-draft" type="button">Export draft JSON</button>
        <label class="file-button" for="import-draft">Import draft JSON</label>
        <input id="import-draft" type="file" accept="application/json,.json">
        <button id="export-json" data-testid="export-json" type="button">Export practice JSON</button>
        <button id="export-csv" data-testid="export-csv" type="button">Export practice CSV</button>
      </div>
    </aside>

    <section class="evidence-panel" data-testid="evidence" aria-label="Synthetic evidence viewer">
      <div class="panel-heading evidence-heading">
        <div><p class="eyebrow" id="case-position">Case</p><h2 id="case-title">Loading…</h2></div>
        <div class="timer" id="timer" data-testid="timer" aria-live="polite">
          <small>Active practice time</small><strong id="timer-value">00:00</strong>
        </div>
      </div>
      <p id="case-challenge" class="case-challenge"></p>
      <div id="comparison-strip" class="comparison-strip" aria-label="Pre and event VV VH comparison">
        <button type="button" data-compare-layer="pre_vv"><img alt="Pre VV comparison thumbnail"><span>Pre VV</span></button>
        <button type="button" data-compare-layer="event_vv"><img alt="Event VV comparison thumbnail"><span>Event VV</span></button>
        <button type="button" data-compare-layer="pre_vh"><img alt="Pre VH comparison thumbnail"><span>Pre VH</span></button>
        <button type="button" data-compare-layer="event_vh"><img alt="Event VH comparison thumbnail"><span>Event VH</span></button>
      </div>
      <div id="layer-switcher" class="layer-switcher" role="group" aria-label="Evidence layer switching">
        <button type="button" data-layer="pre_vv">Pre VV</button>
        <button type="button" data-layer="event_vv">Event VV</button>
        <button type="button" data-layer="pre_vh">Pre VH</button>
        <button type="button" data-layer="event_vh">Event VH</button>
        <button type="button" data-layer="vv_change">VV change</button>
        <button type="button" data-layer="permanent_water">Permanent water</button>
        <button type="button" data-layer="slope">Slope</button>
        <button type="button" data-layer="landcover">Land cover</button>
      </div>
      <div class="viewer-toolbar">
        <label for="zoom-control">Zoom</label>
        <input id="zoom-control" type="range" min="1" max="3" step="0.25" value="1">
        <output id="zoom-value" for="zoom-control">100%</output>
        <button id="pause-timer" type="button" aria-pressed="false">Pause timer</button>
        <button id="undo" type="button">Undo</button>
        <button id="redo" type="button">Redo</button>
        <label for="brush-size">Brush</label>
        <select id="brush-size"><option value="1">1 cell</option><option value="2">2 × 2</option><option value="4">4 × 4</option></select>
      </div>
      <div class="viewer-scroll" id="viewer-scroll">
        <div class="raster-stage" id="raster-stage">
          <img id="layer-image" alt="Selected synthetic SAR evidence layer" width="512" height="512">
          <canvas id="annotation-canvas" data-testid="annotation-canvas" width="512" height="512" tabindex="0" aria-label="32 by 32 practice annotation canvas"></canvas>
        </div>
      </div>
      <p id="layer-caption" class="layer-caption"></p>
      <div id="answer-panel" class="answer-panel" hidden>
        <div><p class="eyebrow">Post-lock feedback</p><h3>Teaching answer</h3></div>
        <img id="answer-image" alt="Synthetic teaching answer mask" width="320" height="320">
        <div id="score-summary" class="score-grid"></div>
        <p id="teaching-rationale"></p>
      </div>
    </section>

    <aside class="annotation-panel" aria-label="Practice annotation controls">
      <div class="panel-heading"><div><p class="eyebrow">Your interpretation</p><h2>Paint the 32 × 32 grid</h2></div></div>
      <div id="class-palette" data-testid="class-palette" class="class-palette" role="group" aria-label="Class palette">
        <button type="button" data-code="0"><span class="swatch dry"></span><b>0</b> Dry land</button>
        <button type="button" data-code="1"><span class="swatch flood"></span><b>1</b> Temporary flood</button>
        <button type="button" data-code="2"><span class="swatch permanent"></span><b>2</b> Permanent or pre-existing water</button>
        <button type="button" data-code="3"><span class="swatch uncertain"></span><b>3</b> Uncertain water change</button>
        <button type="button" data-code="4"><span class="swatch artifact"></span><b>4</b> Unobservable or artifact</button>
        <button type="button" data-code="255"><span class="swatch unreviewed"></span><b>U</b> Erase to unreviewed</button>
      </div>
      <div class="coverage-row"><span>Explicit coverage</span><strong id="coverage-value">0 / 1024</strong></div>
      <button id="fill-unreviewed" type="button">Fill only unreviewed cells with selected class</button>

      <fieldset id="metadata-form">
        <legend>Practice metadata</legend>
        <label for="primary-assessment">Primary assessment</label>
        <select id="primary-assessment">
          <option value="">Choose…</option><option value="dry_land">Dry land</option>
          <option value="temporary_flood">Temporary flood</option>
          <option value="permanent_or_preexisting_water">Permanent or pre-existing water</option>
          <option value="uncertain_water_change">Uncertain water change</option>
          <option value="unobservable_or_artifact">Unobservable or artifact</option>
          <option value="mixed_geometry">Mixed geometry</option>
        </select>
        <label for="confidence" data-testid="confidence">Confidence</label>
        <select id="confidence"><option value="">Choose…</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select>
        <fieldset id="ambiguity" data-testid="ambiguity" class="ambiguity-fieldset">
          <legend>Ambiguity reasons</legend>
          <label><input type="checkbox" value="urban_double_bounce"> Urban double-bounce</label>
          <label><input type="checkbox" value="urban_layover"> Urban layover</label>
          <label><input type="checkbox" value="radar_shadow"> Radar shadow</label>
          <label><input type="checkbox" value="steep_terrain"> Steep terrain</label>
          <label><input type="checkbox" value="wet_soil_or_agricultural_change"> Wet soil or agricultural change</label>
          <label><input type="checkbox" value="flooded_vegetation"> Flooded vegetation</label>
          <label><input type="checkbox" value="permanent_water_boundary"> Permanent-water boundary</label>
          <label><input type="checkbox" value="speckle_or_isolated_response"> Speckle or isolated response</label>
          <label><input type="checkbox" value="pre_post_misregistration"> Pre/post misregistration</label>
          <label><input type="checkbox" value="temporal_mismatch"> Temporal mismatch</label>
          <label><input type="checkbox" value="other"> Other</label>
        </fieldset>
        <label for="notes" data-testid="notes">Reasoning notes</label>
        <textarea id="notes" rows="4" maxlength="1000" placeholder="What evidence supports your interpretation?"></textarea>
      </fieldset>

      <div class="lock-box" data-testid="lock">
        <section id="pre-lock-readiness" data-testid="pre-lock-readiness" class="readiness-panel" aria-labelledby="readiness-title">
          <div class="readiness-heading">
            <h3 id="readiness-title">Pre-lock readiness</h3>
            <strong id="readiness-summary" aria-live="polite">0 / 6 ready</strong>
          </div>
          <p>Every item is required for this synthetic practice attempt. These checks improve learning quality only; they do not authorize formal review.</p>
          <ul id="readiness-checklist" class="readiness-checklist" aria-live="polite"></ul>
        </section>
        <p id="lock-message" aria-live="polite">Complete every pre-lock readiness item, then lock this practice attempt.</p>
        <button id="lock-attempt" type="button" class="primary-action">Lock practice attempt</button>
        <button id="reveal-answer" data-testid="reveal-answer" type="button" disabled>Reveal teaching answer</button>
      </div>
      <details class="contract-note">
        <summary>Why these outputs are not formal labels</summary>
        <p>Downloads record <code>locked_at_utc</code> and <code>duration_seconds</code> for learning feedback only. They do not use a formal annotation schema.</p>
        <p><code>eligible_for_query_model_training=false</code><br><code>eligible_for_fpps=false</code></p>
      </details>
    </aside>
  </main>
  <dialog id="lock-dialog" class="lock-dialog" aria-labelledby="lock-dialog-title">
    <h2 id="lock-dialog-title">Lock this practice attempt?</h2>
    <p>This freezes your first answer for this synthetic case. You can still reveal feedback and export it, but you cannot edit it afterward.</p>
    <form method="dialog" class="dialog-actions">
      <button type="submit" value="cancel">Continue reviewing</button>
      <button id="confirm-lock" type="submit" value="confirm" class="primary-action">Lock practice attempt</button>
    </form>
  </dialog>
  <div id="toast" class="toast" role="status" aria-live="polite"></div>
  <script src="workspace_data.js"></script>
  <script src="app.js"></script>
</body>
</html>
"""


_STYLES_CSS = r"""
:root{color-scheme:light;--ink:#14231f;--muted:#60706a;--bg:#eef3f1;--panel:#fff;--line:#d5e0dc;--brand:#0d6b61;--brand-dark:#074b45;--amber:#d99517;--danger:#b33a3a;--shadow:0 14px 36px rgba(18,47,39,.09);--radius:12px;font-family:"Segoe UI",Inter,Arial,sans-serif}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-size:14px;line-height:1.45}.practice-banner{position:sticky;top:0;z-index:100;background:#6b2c00;color:#fff4df;text-align:center;padding:8px 16px;font-weight:800;letter-spacing:.08em}.app-header{display:flex;justify-content:space-between;gap:24px;align-items:center;padding:20px 28px;background:#f9fbfa;border-bottom:1px solid var(--line)}h1,h2,h3,p{margin-top:0}h1{margin-bottom:4px;font-size:26px}h2{font-size:18px;margin:0}.eyebrow{margin:0 0 4px;text-transform:uppercase;letter-spacing:.11em;font-size:11px;font-weight:800;color:var(--brand)}.header-badges{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}.badge{padding:6px 10px;border-radius:999px;background:#e8efec;border:1px solid var(--line);font-size:12px;font-weight:700}.badge.practice{background:#fff0d4;border-color:#efbf66;color:#6b3d00}.hold-card{margin:16px 28px 10px;padding:14px 18px;border:1px solid #e3b65c;border-left:5px solid var(--amber);background:#fff9e9;border-radius:10px}.hold-card>div{display:flex;gap:12px;justify-content:space-between}.hold-card p{margin:7px 0 0;color:#624d25}.safety-line{font-weight:700}.workflow-strip{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:10px 28px 16px}.workflow-step{display:grid;grid-template-columns:28px 1fr;gap:2px 8px;background:#f8faf9;border:1px solid var(--line);border-radius:9px;padding:10px}.workflow-step span{grid-row:1/3;width:26px;height:26px;display:grid;place-items:center;border-radius:50%;background:#dfe8e4;font-weight:800}.workflow-step small{color:var(--muted)}.workflow-step.active{border-color:#66ab9e;background:#edf8f5}.workflow-step.active span{background:var(--brand);color:white}.workflow-step.held{opacity:.74}.workspace{display:grid;grid-template-columns:minmax(230px,280px) minmax(560px,1fr) minmax(290px,350px);gap:14px;padding:0 18px 22px;align-items:start}.queue-panel,.evidence-panel,.annotation-panel{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);min-width:0}.queue-panel,.annotation-panel{padding:16px;position:sticky;top:48px;max-height:calc(100vh - 66px);overflow:auto}.evidence-panel{padding:18px}.panel-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}.progress-track{height:7px;border-radius:99px;background:#e8efec;overflow:hidden;margin-bottom:12px}.progress-track span{display:block;height:100%;width:0;background:var(--brand);transition:width .18s}.case-list{display:grid;gap:5px;max-height:48vh;overflow:auto;padding-right:3px}.case-item{display:grid;grid-template-columns:1fr auto;gap:4px 8px;text-align:left;border:1px solid var(--line);background:#f8faf9;border-radius:8px;padding:9px;cursor:pointer}.case-item small{grid-column:1/3;color:var(--muted)}.case-item.active{border-color:var(--brand);box-shadow:0 0 0 2px rgba(13,107,97,.12)}.case-item.locked .case-status{color:var(--brand);font-weight:800}.queue-actions{display:grid;gap:7px;margin-top:14px}.file-button,button,select,input,textarea{font:inherit}button,.file-button{border:1px solid #bfcfc9;border-radius:8px;background:#f5f8f7;color:var(--ink);padding:9px 11px;cursor:pointer;font-weight:650;text-align:center}button:hover,.file-button:hover{border-color:var(--brand);background:#edf7f4}button:focus-visible,.file-button:focus-visible,select:focus-visible,input:focus-visible,textarea:focus-visible,canvas:focus-visible{outline:3px solid #65aee8;outline-offset:2px}button:disabled{opacity:.48;cursor:not-allowed}input[type=file]{position:absolute;left:-9999px}.evidence-heading{align-items:flex-start}.timer{text-align:right;padding:7px 11px;border-radius:8px;background:#edf6f3;min-width:128px}.timer small{display:block;color:var(--muted)}.timer strong{font-size:21px;font-variant-numeric:tabular-nums}.case-challenge{padding:10px 12px;background:#f5f8f7;border-radius:8px}.comparison-strip{display:grid;grid-template-columns:repeat(4,minmax(90px,1fr));gap:7px;margin:10px 0 12px}.comparison-strip button{padding:5px;background:#07141d;color:#eef8f5}.comparison-strip button.active{box-shadow:0 0 0 3px #65aee8;border-color:#65aee8}.comparison-strip img{display:block;width:100%;aspect-ratio:1;object-fit:cover;image-rendering:pixelated;margin-bottom:4px}.layer-switcher{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin:12px 0}.layer-switcher button{padding:7px;font-size:12px}.layer-switcher button.active{background:var(--brand);color:#fff;border-color:var(--brand)}.viewer-toolbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px}.viewer-toolbar input[type=range]{width:120px}.viewer-scroll{overflow:auto;max-height:610px;background:#07141d;border-radius:10px;padding:14px;display:grid;place-items:center}.raster-stage{position:relative;width:512px;height:512px;flex:none}.raster-stage img,.raster-stage canvas{position:absolute;inset:0;width:100%;height:100%;image-rendering:pixelated}.raster-stage img{background:#03080b}.raster-stage canvas{touch-action:none;cursor:crosshair}.layer-caption{margin:9px 0;color:var(--muted)}.class-palette{display:grid;gap:6px}.class-palette button{display:grid;grid-template-columns:18px 22px 1fr;align-items:center;text-align:left;padding:8px}.class-palette button.active{box-shadow:0 0 0 2px var(--brand);border-color:var(--brand)}.swatch{width:16px;height:16px;border-radius:4px;border:1px solid rgba(0,0,0,.2)}.dry{background:#787878}.flood{background:#2371d2}.permanent{background:#37cdda}.uncertain{background:#f5c242}.artifact{background:#ca43c4}.unreviewed{background:#050505}.coverage-row{display:flex;justify-content:space-between;margin:12px 0 8px;padding:8px;background:#f4f7f6;border-radius:7px}fieldset{border:1px solid var(--line);border-radius:9px;margin:14px 0;padding:12px}legend{font-weight:800}label{font-weight:650}select,textarea{width:100%;border:1px solid #bdccc6;border-radius:7px;background:#fff;padding:8px;margin:4px 0 10px}.ambiguity-fieldset{display:grid;grid-template-columns:1fr;gap:5px;margin:10px 0}.ambiguity-fieldset label{font-weight:500}.ambiguity-fieldset input{margin-right:6px}.lock-box{border-top:1px solid var(--line);padding-top:13px}.lock-box p{color:var(--muted)}.primary-action{width:100%;background:var(--brand);border-color:var(--brand);color:white}.primary-action:hover{background:var(--brand-dark)}#reveal-answer{width:100%;margin-top:7px}.contract-note{margin-top:14px;color:var(--muted)}.answer-panel{margin-top:18px;border-top:1px solid var(--line);padding-top:16px}.answer-panel img{width:320px;max-width:100%;image-rendering:pixelated;border:1px solid var(--line);border-radius:8px}.score-grid{display:grid;grid-template-columns:repeat(3,minmax(110px,1fr));gap:8px;margin:10px 0}.score-card{padding:10px;background:#edf6f3;border-radius:8px}.score-card small{display:block;color:var(--muted)}.score-card strong{font-size:19px}.toast{position:fixed;right:18px;bottom:18px;max-width:420px;background:#173e37;color:white;padding:11px 15px;border-radius:8px;box-shadow:var(--shadow);opacity:0;pointer-events:none;transform:translateY(8px);transition:.15s}.toast.show{opacity:1;transform:none}.toast.error{background:#7d2020}@media(max-width:1250px){.workspace{grid-template-columns:240px minmax(480px,1fr)}.annotation-panel{position:static;grid-column:1/3;max-height:none}.queue-panel{top:44px}.workflow-strip{grid-template-columns:repeat(3,1fr)}}@media(max-width:820px){.app-header{align-items:flex-start;flex-direction:column}.workspace{grid-template-columns:1fr}.queue-panel,.annotation-panel{position:static;grid-column:auto;max-height:none}.workflow-strip{grid-template-columns:1fr 1fr}.layer-switcher,.comparison-strip{grid-template-columns:repeat(2,1fr)}.viewer-scroll{max-height:520px}.raster-stage{width:448px;height:448px}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important}}
.readiness-panel{margin-bottom:13px;padding:12px;border:1px solid var(--line);border-radius:9px;background:#f8faf9}.readiness-heading{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin-bottom:6px}.readiness-heading h3{font-size:15px;margin:0}.readiness-heading strong{font-size:12px;color:var(--danger)}.readiness-panel.complete{border-color:#75b2a7;background:#edf8f5}.readiness-panel.complete .readiness-heading strong{color:var(--brand)}.readiness-panel>p{font-size:12px;margin:0 0 9px;color:var(--muted)}.readiness-checklist{display:grid;gap:6px;list-style:none;margin:0;padding:0}.readiness-checklist li{display:grid;grid-template-columns:auto 1fr;gap:7px;align-items:start;padding:6px 7px;border-radius:7px;background:#fff;border:1px solid var(--line);font-size:12px}.readiness-checklist .readiness-state{min-width:48px;border-radius:999px;padding:1px 6px;text-align:center;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.04em}.readiness-checklist li.ready .readiness-state{background:#d9eee9;color:var(--brand-dark)}.readiness-checklist li.missing .readiness-state{background:#fee8e5;color:#842d2d}.lock-dialog{max-width:460px;border:1px solid var(--line);border-radius:12px;padding:22px;box-shadow:0 22px 70px rgba(10,32,27,.28);color:var(--ink)}.lock-dialog::backdrop{background:rgba(7,20,29,.58)}.lock-dialog p{color:var(--muted)}.dialog-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:18px}.dialog-actions .primary-action{width:auto}
"""


_APP_JS = r"""
'use strict';
(() => {
  const config = window.FloodGuardPracticeWorkspace;
  if (!config || config.practiceOnly !== true || config.conceptualTeachingOnly !== true) {
    document.body.textContent = 'BLOCKED: invalid practice workspace data.';
    return;
  }
  const CODES = [0, 1, 2, 3, 4, 255];
  const LABELS = {0:'dry_land',1:'temporary_flood',2:'permanent_or_preexisting_water',3:'uncertain_water_change',4:'unobservable_or_artifact',255:'unreviewed'};
  const COLORS = {0:'rgba(120,120,120,.64)',1:'rgba(35,113,210,.68)',2:'rgba(55,205,218,.68)',3:'rgba(245,194,66,.70)',4:'rgba(202,67,196,.70)',255:'rgba(0,0,0,0)'};
  const REQUIRED_LAYER_IDS = ['pre_vv','event_vv','pre_vh','event_vh','vv_change','permanent_water','slope','landcover'];
  const PRIMARY_CODES = {dry_land:0,temporary_flood:1,permanent_or_preexisting_water:2,uncertain_water_change:3,unobservable_or_artifact:4};
  const storageKey = `floodguard-reviewer-practice:${config.workspaceId}`;
  const state = {caseIndex:0, selectedCode:255, brush:1, layer:'pre_vv', zoom:1, drawing:false, lastCell:-1, paused:false, tick:performance.now(), answerLoading:new Set(), attempts:{}};
  let saveTimer = null;
  let toastTimer = null;
  const byId = id => document.getElementById(id);
  const canvas = byId('annotation-canvas');
  const context = canvas.getContext('2d');

  function newAttempt() {
    return {labels:Array(1024).fill(255),history:[],future:[],locked:false,revealed:false,started_at_utc:'',locked_at_utc:'',duration_seconds:0,confidence:'',primaryAssessment:'',ambiguity:[],notes:'',visitedLayers:[],score:null};
  }
  config.cases.forEach(item => { state.attempts[item.caseId] = newAttempt(); });

  function currentCase(){ return config.cases[state.caseIndex]; }
  function currentAttempt(){ return state.attempts[currentCase().caseId]; }
  function utcNow(){ return new Date().toISOString().replace(/\.\d{3}Z$/,'Z'); }
  function safeText(value){ return String(value == null ? '' : value); }
  function startAttempt(){ const attempt=currentAttempt(); if(!attempt.started_at_utc && !attempt.locked){ attempt.started_at_utc=utcNow(); scheduleSave(); } }
  function accrue(){ const now=performance.now(); const delta=Math.min(2,(now-state.tick)/1000); state.tick=now; const attempt=currentAttempt(); if(!document.hidden && document.hasFocus() && !state.paused && !attempt.locked && attempt.started_at_utc){ attempt.duration_seconds += Math.max(0,delta); updateTimer(); } }
  setInterval(accrue,1000); window.addEventListener('blur',accrue); document.addEventListener('visibilitychange',accrue);

  function updateTimer(){ const seconds=Math.floor(currentAttempt().duration_seconds); const minutes=Math.floor(seconds/60); byId('timer-value').textContent=`${String(minutes).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`; }
  function scheduleSave(){ clearTimeout(saveTimer); saveTimer=setTimeout(saveLocal,180); }
  function saveLocal(){
    const payload={artifact_schema:'floodguard.reviewer_practice_draft.v1',workspace_id:config.workspaceId,reviewer_display_name:config.reviewerDisplayName,saved_at_utc:utcNow(),case_index:state.caseIndex,attempts:state.attempts};
    try { localStorage.setItem(storageKey,JSON.stringify(payload)); } catch(error){ showToast('Browser autosave is unavailable. Export a draft JSON.',true); }
  }
  function restoreLocal(){
    try { const raw=localStorage.getItem(storageKey); if(raw) applyDraft(JSON.parse(raw),false); } catch(error){ showToast('Saved browser draft could not be restored.',true); }
  }
  function sanitizeAttempt(raw){
    const clean=newAttempt(); if(!raw || !Array.isArray(raw.labels) || raw.labels.length!==1024) return clean;
    clean.labels=raw.labels.map(value => CODES.includes(Number(value)) ? Number(value) : 255);
    clean.locked=raw.locked===true; clean.revealed=clean.locked && raw.revealed===true;
    clean.started_at_utc=safeText(raw.started_at_utc); clean.locked_at_utc=clean.locked?safeText(raw.locked_at_utc):'';
    clean.duration_seconds=Number.isFinite(Number(raw.duration_seconds))?Math.max(0,Number(raw.duration_seconds)):0;
    clean.confidence=['high','medium','low'].includes(raw.confidence)?raw.confidence:'';
    clean.primaryAssessment=['dry_land','temporary_flood','permanent_or_preexisting_water','uncertain_water_change','unobservable_or_artifact','mixed_geometry'].includes(raw.primaryAssessment)?raw.primaryAssessment:'';
    clean.ambiguity=Array.isArray(raw.ambiguity)?raw.ambiguity.map(safeText).filter(value=>value.length<=80):[];
    clean.notes=safeText(raw.notes).slice(0,1000); clean.visitedLayers=Array.isArray(raw.visitedLayers)?Array.from(new Set(raw.visitedLayers.map(safeText).filter(value=>REQUIRED_LAYER_IDS.includes(value)))):[];
    clean.score=clean.locked && raw.score && typeof raw.score==='object'?raw.score:null; return clean;
  }
  function applyDraft(payload,notify=true){
    if(!payload || payload.artifact_schema!=='floodguard.reviewer_practice_draft.v1' || payload.workspace_id!==config.workspaceId || payload.reviewer_display_name!==config.reviewerDisplayName) throw new Error('Draft does not belong to this practice workspace and reviewer.');
    const attempts={}; config.cases.forEach(item => { attempts[item.caseId]=sanitizeAttempt(payload.attempts && payload.attempts[item.caseId]); }); state.attempts=attempts;
    state.caseIndex=Math.min(config.cases.length-1,Math.max(0,Number(payload.case_index)||0)); state.tick=performance.now(); renderAll(); if(notify) showToast('Practice draft imported.');
  }

  function renderAll(){ renderHold(); renderNavigation(); renderCase(); renderPalette(); updateProgress(); }
  function renderHold(){ byId('hold-state').textContent=config.formalHold.active?'ACTIVE · read-only':'Unavailable · formal access still disabled'; byId('hold-reason').textContent=config.formalHold.reason; }
  function renderNavigation(){
    const host=byId('case-nav'); host.replaceChildren(); config.cases.forEach((item,index)=>{ const attempt=state.attempts[item.caseId]; const button=document.createElement('button'); button.type='button'; button.className=`case-item${index===state.caseIndex?' active':''}${attempt.locked?' locked':''}`; button.setAttribute('role','listitem'); button.dataset.caseIndex=String(index);
      const name=document.createElement('strong'); name.textContent=item.caseId; const status=document.createElement('span'); status.className='case-status'; status.textContent=attempt.locked?'Locked':'Open'; const prompt=document.createElement('small'); prompt.textContent='Inspect all evidence layers and paint the complete grid.'; button.append(name,status,prompt); button.addEventListener('click',()=>switchCase(index)); host.append(button); });
  }
  function switchCase(index){ accrue(); state.caseIndex=index; state.layer='pre_vv'; state.tick=performance.now(); renderAll(); scheduleSave(); }
  function renderCase(){
    const item=currentCase(),attempt=currentAttempt(); byId('case-position').textContent=`Case ${state.caseIndex+1} of ${config.cases.length}`; byId('case-title').textContent=item.caseId; byId('case-challenge').textContent='Blinded practice prompt: inspect every available layer, then paint the complete cell geometry before revealing the teaching answer.';
    byId('primary-assessment').value=attempt.primaryAssessment; byId('confidence').value=attempt.confidence; byId('notes').value=attempt.notes; document.querySelectorAll('#ambiguity input').forEach(input=>{input.checked=attempt.ambiguity.includes(input.value);input.disabled=attempt.locked;});
    byId('primary-assessment').disabled=attempt.locked; byId('confidence').disabled=attempt.locked; byId('notes').disabled=attempt.locked; byId('fill-unreviewed').disabled=attempt.locked; byId('reveal-answer').disabled=!attempt.locked; byId('lock-attempt').textContent=attempt.locked?'Practice attempt locked':'Lock practice attempt';
    updateComparisonStrip(); updateLayer(); updateCoverage(); updateTimer(); updatePauseButton(); draw(); if(attempt.revealed) revealAnswer(); else {byId('answer-panel').hidden=true;byId('reveal-answer').textContent='Reveal teaching answer';}
  }
  function panelById(id){ return currentCase().panels.find(panel=>panel.id===id) || currentCase().panels[0]; }
  function updateLayer(explicitVisit=false){ const panel=panelById(state.layer); state.layer=panel.id; byId('layer-image').src=panel.path; byId('layer-image').alt=`${currentCase().caseId}: ${panel.label} conceptual teaching layer`; byId('layer-caption').textContent=`Showing ${panel.label}. Brighter grayscale means greater conceptual return; VV change uses red for positive pre − event and blue for negative change.`; document.querySelectorAll('#layer-switcher button').forEach(button=>button.classList.toggle('active',button.dataset.layer===state.layer)); const attempt=currentAttempt(); if(explicitVisit&&!attempt.locked&&!attempt.visitedLayers.includes(state.layer)){attempt.visitedLayers.push(state.layer);startAttempt();scheduleSave();} updateReadiness(); }
  function updateComparisonStrip(){ document.querySelectorAll('#comparison-strip button').forEach(button=>{const panel=panelById(button.dataset.compareLayer);const image=button.querySelector('img');image.src=panel.path;image.alt=`${currentCase().caseId}: ${panel.label} comparison thumbnail`;button.classList.toggle('active',panel.id===state.layer);}); }
  function updatePauseButton(){const button=byId('pause-timer');button.textContent=state.paused?'Resume timer':'Pause timer';button.setAttribute('aria-pressed',String(state.paused));button.disabled=currentAttempt().locked;}
  function renderPalette(){
    document.querySelectorAll('#class-palette button').forEach(button=>{button.classList.toggle('active',Number(button.dataset.code)===state.selectedCode);button.disabled=currentAttempt().locked;});
    const fillButton=byId('fill-unreviewed');
    fillButton.disabled=currentAttempt().locked||state.selectedCode===255;
    fillButton.textContent=state.selectedCode===255?'Choose class 0–4 before filling unreviewed cells':'Fill only unreviewed cells with selected class';
  }
  function readinessItems(attempt=currentAttempt()){
    const missingCells=attempt.labels.filter(code=>code===255).length;
    const visited=new Set(attempt.visitedLayers.filter(layer=>REQUIRED_LAYER_IDS.includes(layer)));
    const missingLayers=REQUIRED_LAYER_IDS.filter(layer=>!visited.has(layer));
    const missingLayerLabels=missingLayers.map(layer=>panelById(layer).label);
    const noteLength=attempt.notes.replace(/\s/g,'').length;
    const paintedCodes=new Set(attempt.labels.filter(code=>code!==255));
    const needsAmbiguity=attempt.labels.some(code=>code===3||code===4);
    let primaryReady=false;
    let primaryMessage='Select a primary assessment.';
    let primaryError='primary assessment is missing';
    if(attempt.primaryAssessment==='mixed_geometry'){
      primaryReady=paintedCodes.size>=2;
      primaryMessage=primaryReady?`Mixed geometry is supported by ${paintedCodes.size} painted class codes.`:`Mixed geometry needs at least two painted class codes; ${paintedCodes.size} currently present.`;
      primaryError='mixed geometry requires at least two painted class codes';
    } else if(Object.hasOwn(PRIMARY_CODES,attempt.primaryAssessment)){
      const primaryCode=PRIMARY_CODES[attempt.primaryAssessment];
      const matchingCells=attempt.labels.filter(code=>code===primaryCode).length;
      primaryReady=matchingCells>0;
      primaryMessage=primaryReady?`Primary assessment has ${matchingCells} matching painted cells.`:`Primary assessment has no matching code ${primaryCode} cells.`;
      primaryError='selected primary assessment has no matching painted cells';
    }
    return [
      {id:'coverage',ready:missingCells===0,message:missingCells===0?'All 1,024 cells have an explicit class.':`${missingCells} cells remain unreviewed.`,error:`${missingCells} cells remain unreviewed`},
      {id:'evidence',ready:missingLayers.length===0,message:missingLayers.length===0?'All eight evidence layers were explicitly visited.':`${visited.size} / 8 evidence layers visited; still visit ${missingLayerLabels.join(', ')}.`,error:`all eight evidence layers must be explicitly visited (${visited.size}/8 visited)`},
      {id:'primary',ready:primaryReady,message:primaryMessage,error:primaryError},
      {id:'confidence',ready:Boolean(attempt.confidence),message:attempt.confidence?`Confidence recorded as ${attempt.confidence}.`:'Select high, medium, or low confidence.',error:'confidence is missing'},
      {id:'ambiguity',ready:!needsAmbiguity||attempt.ambiguity.length>0,message:needsAmbiguity?(attempt.ambiguity.length?`${attempt.ambiguity.length} ambiguity reason${attempt.ambiguity.length===1?'':'s'} recorded.`:'Uncertain or artifact cells need at least one ambiguity reason.'):'No uncertain or artifact cells require an ambiguity reason.',error:'uncertain/artifact cells require an ambiguity reason'},
      {id:'reasoning',ready:noteLength>=20,message:`Reasoning note contains ${noteLength} / 20 required non-whitespace characters.`,error:`reasoning note needs ${Math.max(0,20-noteLength)} more non-whitespace characters`},
    ];
  }
  function updateReadiness(){
    const attempt=currentAttempt();
    const items=readinessItems(attempt);
    const host=byId('readiness-checklist');
    host.replaceChildren();
    items.forEach(item=>{const row=document.createElement('li');row.className=item.ready?'ready':'missing';row.dataset.requirement=item.id;const stateLabel=document.createElement('span');stateLabel.className='readiness-state';stateLabel.textContent=item.ready?'Ready':'Missing';const message=document.createElement('span');message.textContent=item.message;row.append(stateLabel,message);host.append(row);});
    const readyCount=items.filter(item=>item.ready).length;
    const allReady=readyCount===items.length;
    byId('readiness-summary').textContent=attempt.locked?`${readyCount} / ${items.length} recorded at lock`:`${readyCount} / ${items.length} ready`;
    byId('pre-lock-readiness').classList.toggle('complete',allReady);
    byId('lock-attempt').disabled=attempt.locked||!allReady;
    if(attempt.locked)byId('lock-message').textContent=`Locked at ${attempt.locked_at_utc}. This practice attempt cannot be edited.`;
    else if(allReady)byId('lock-message').textContent='All pre-lock checks are ready. Review the grid once more, then lock this practice attempt.';
    else byId('lock-message').textContent=`${items.length-readyCount} pre-lock requirement${items.length-readyCount===1?' remains':'s remain'}. Complete every checklist item before locking.`;
    return items;
  }
  function updateCoverage(){ const reviewed=currentAttempt().labels.filter(code=>code!==255).length; byId('coverage-value').textContent=`${reviewed} / 1024`; updateReadiness(); }
  function updateProgress(){ const locked=config.cases.filter(item=>state.attempts[item.caseId].locked).length; byId('progress-count').textContent=`${locked} / ${config.cases.length} locked`; byId('progress-bar').style.width=`${(locked/config.cases.length)*100}%`; }

  function pushHistory(){ const attempt=currentAttempt(); attempt.history.push(attempt.labels.slice()); if(attempt.history.length>60) attempt.history.shift(); attempt.future=[]; }
  function paintCell(row,column){ const attempt=currentAttempt(); if(attempt.locked)return; startAttempt(); const size=state.brush; const offset=Math.floor((size-1)/2); for(let r=row-offset;r<row-offset+size;r++){for(let c=column-offset;c<column-offset+size;c++){if(r>=0&&r<32&&c>=0&&c<32)attempt.labels[r*32+c]=state.selectedCode;}} draw();updateCoverage();scheduleSave(); }
  function pointerCell(event){ const rect=canvas.getBoundingClientRect(); const column=Math.max(0,Math.min(31,Math.floor((event.clientX-rect.left)/rect.width*32))); const row=Math.max(0,Math.min(31,Math.floor((event.clientY-rect.top)/rect.height*32))); return row*32+column; }
  canvas.addEventListener('pointerdown',event=>{if(currentAttempt().locked)return;canvas.setPointerCapture(event.pointerId);pushHistory();state.drawing=true;state.lastCell=-1;const cell=pointerCell(event);state.lastCell=cell;paintCell(Math.floor(cell/32),cell%32);});
  canvas.addEventListener('pointermove',event=>{if(!state.drawing)return;const cell=pointerCell(event);if(cell!==state.lastCell){state.lastCell=cell;paintCell(Math.floor(cell/32),cell%32);}}); window.addEventListener('pointerup',()=>{state.drawing=false;state.lastCell=-1;});
  function draw(){ context.clearRect(0,0,512,512); const labels=currentAttempt().labels; for(let index=0;index<1024;index++){const code=labels[index];if(code===255)continue;context.fillStyle=COLORS[code];context.fillRect((index%32)*16,Math.floor(index/32)*16,16,16);} context.strokeStyle='rgba(255,255,255,.22)';context.lineWidth=.5;for(let i=0;i<=32;i++){context.beginPath();context.moveTo(i*16,0);context.lineTo(i*16,512);context.stroke();context.beginPath();context.moveTo(0,i*16);context.lineTo(512,i*16);context.stroke();} }
  function undo(){const attempt=currentAttempt();if(attempt.locked||!attempt.history.length)return;attempt.future.push(attempt.labels.slice());attempt.labels=attempt.history.pop();draw();updateCoverage();scheduleSave();}
  function redo(){const attempt=currentAttempt();if(attempt.locked||!attempt.future.length)return;attempt.history.push(attempt.labels.slice());attempt.labels=attempt.future.pop();draw();updateCoverage();scheduleSave();}

  function lockAttempt(){
    const attempt=currentAttempt(); if(attempt.locked)return; accrue(); const errors=readinessItems(attempt).filter(item=>!item.ready).map(item=>item.error); if(errors.length){updateReadiness();showToast(`Cannot lock: ${errors.join('; ')}.`,true);return;}
    byId('lock-dialog').showModal();
  }
  function confirmLock(event){const attempt=currentAttempt();if(attempt.locked)return;const errors=readinessItems(attempt).filter(item=>!item.ready).map(item=>item.error);if(errors.length){event.preventDefault();updateReadiness();showToast(`Cannot lock: ${errors.join('; ')}.`,true);return;}attempt.locked=true;attempt.locked_at_utc=utcNow();attempt.history=[];attempt.future=[];saveLocal();renderAll();showToast('Practice attempt locked. You may now reveal the teaching answer.');}
  function revealAnswer(){
    const attempt=currentAttempt(),item=currentCase(); if(!attempt.locked){showToast('Lock the practice attempt before revealing the answer.',true);return;} if(window.FloodGuardPracticeAnswers&&window.FloodGuardPracticeAnswers[item.caseId]){showAnswer(window.FloodGuardPracticeAnswers[item.caseId]);return;} if(state.answerLoading.has(item.caseId))return; state.answerLoading.add(item.caseId); const script=document.createElement('script');script.src=item.revealScript;script.onload=()=>{state.answerLoading.delete(item.caseId);const answer=window.FloodGuardPracticeAnswers&&window.FloodGuardPracticeAnswers[item.caseId];if(!answer){showToast('Answer package did not load.',true);return;}showAnswer(answer);};script.onerror=()=>{state.answerLoading.delete(item.caseId);showToast('Answer package could not be opened. Keep the workspace files together.',true);};document.head.append(script);
  }
  function showAnswer(answer){
    const attempt=currentAttempt(); if(!attempt.locked)return; const metrics=score(attempt.labels,answer.codes);attempt.score=metrics;attempt.revealed=true;byId('answer-image').src=answer.answerPath;byId('answer-panel').hidden=false;byId('score-summary').replaceChildren(scoreCard('Overall accuracy',formatPercent(metrics.accuracy)),scoreCard('Temporary-flood Dice',formatPercent(metrics.temporary_flood_dice)),scoreCard('Correct cells',`${metrics.correct_cells} / 1024`));byId('teaching-rationale').textContent=`Teaching scenario: ${answer.teachingChallenge || 'synthetic interpretation exercise'}. Expected primary: ${answer.expectedPrimary || 'mixed geometry'}. ${answer.teachingRationale || ''}`;byId('reveal-answer').textContent='Teaching answer revealed';scheduleSave();
  }
  function score(labels,answer){let correct=0,tp=0,fp=0,fn=0;for(let i=0;i<1024;i++){if(labels[i]===answer[i])correct++;if(labels[i]===1&&answer[i]===1)tp++;else if(labels[i]===1&&answer[i]!==1)fp++;else if(labels[i]!==1&&answer[i]===1)fn++;}const denominator=2*tp+fp+fn;return{accuracy:correct/1024,temporary_flood_dice:denominator?2*tp/denominator:1,correct_cells:correct,true_positive:tp,false_positive:fp,false_negative:fn};}
  function scoreCard(label,value){const card=document.createElement('div');card.className='score-card';const small=document.createElement('small');small.textContent=label;const strong=document.createElement('strong');strong.textContent=value;card.append(small,strong);return card;}
  function formatPercent(value){return `${(Number(value)*100).toFixed(1)}%`;}

  function practiceEnvelope(){
    const rows=config.cases.map(item=>{const a=state.attempts[item.caseId];return{practice_case_id:item.caseId,locked:a.locked,started_at_utc:a.started_at_utc,locked_at_utc:a.locked_at_utc,duration_seconds:Number(a.duration_seconds.toFixed(1)),primary_assessment:a.primaryAssessment,confidence:a.confidence,ambiguity_reason_codes:a.ambiguity,evidence_layers_viewed:a.visitedLayers,notes:a.notes,practice_cell_codes:a.labels,post_lock_feedback_revealed:a.revealed,practice_score:a.score};});
    return{artifact_schema:'floodguard.reviewer_practice_export.v1',workspace_id:config.workspaceId,reviewer_display_name:config.reviewerDisplayName,exported_at_utc:utcNow(),practice_only:true,conceptual_teaching_only:true,formal_review_authorized:false,formal_reviewer_calibration:false,real_event_queries_used:false,eligible_for_reviewer_calibration:false,eligible_for_agreement:false,eligible_for_consensus:false,eligible_for_query_model_training:false,eligible_for_model_evaluation:false,eligible_for_decision_layer:false,eligible_for_fpps:false,eligible_for_warning:false,cases:rows};
  }
  function download(name,content,type){const blob=new Blob([content],{type});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download=name;document.body.append(link);link.click();setTimeout(()=>{URL.revokeObjectURL(link.href);link.remove();},0);}
  function exportDraft(){accrue();const payload={artifact_schema:'floodguard.reviewer_practice_draft.v1',workspace_id:config.workspaceId,reviewer_display_name:config.reviewerDisplayName,saved_at_utc:utcNow(),case_index:state.caseIndex,attempts:state.attempts};download('floodguard_practice_draft.json',JSON.stringify(payload,null,2),'application/json;charset=utf-8');}
  function exportPracticeJson(){accrue();download('floodguard_practice_session.json',JSON.stringify(practiceEnvelope(),null,2),'application/json;charset=utf-8');}
  function csvCell(value){const text=String(value==null?'':value);return `"${text.replaceAll('"','""')}"`;}
  function exportPracticeCsv(){accrue();const header=['practice_workspace_id','practice_case_id','reviewer_display_name','locked_at_utc','duration_seconds','confidence','row_index','column_index','practice_label_code','practice_label_name','post_lock_feedback_revealed'];const lines=[header.map(csvCell).join(',')];config.cases.forEach(item=>{const a=state.attempts[item.caseId];a.labels.forEach((code,index)=>lines.push([config.workspaceId,item.caseId,config.reviewerDisplayName,a.locked_at_utc,Number(a.duration_seconds.toFixed(1)),a.confidence,Math.floor(index/32),index%32,code,LABELS[code],a.revealed].map(csvCell).join(',')));});download('floodguard_practice_cells.csv',lines.join('\r\n')+'\r\n','text/csv;charset=utf-8');}

  function showToast(message,error=false){const toast=byId('toast');toast.textContent=message;toast.classList.toggle('error',error);toast.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>toast.classList.remove('show'),4200);}
  document.querySelectorAll('#layer-switcher button').forEach(button=>button.addEventListener('click',()=>{state.layer=button.dataset.layer;updateLayer(true);}));
  document.querySelectorAll('#comparison-strip button').forEach(button=>button.addEventListener('click',()=>{state.layer=button.dataset.compareLayer;updateComparisonStrip();updateLayer(true);}));
  document.querySelectorAll('#class-palette button').forEach(button=>button.addEventListener('click',()=>{state.selectedCode=Number(button.dataset.code);renderPalette();canvas.focus();}));
  byId('zoom-control').addEventListener('input',event=>{state.zoom=Number(event.target.value);const size=512*state.zoom;byId('raster-stage').style.width=`${size}px`;byId('raster-stage').style.height=`${size}px`;byId('zoom-value').textContent=`${Math.round(state.zoom*100)}%`;});
  byId('pause-timer').addEventListener('click',()=>{accrue();state.paused=!state.paused;state.tick=performance.now();updatePauseButton();showToast(state.paused?'Practice timer paused.':'Practice timer resumed.');});
  byId('brush-size').addEventListener('change',event=>{state.brush=Number(event.target.value);}); byId('undo').addEventListener('click',undo);byId('redo').addEventListener('click',redo);
  byId('fill-unreviewed').addEventListener('click',()=>{const attempt=currentAttempt();if(attempt.locked||state.selectedCode===255)return;startAttempt();pushHistory();attempt.labels=attempt.labels.map(code=>code===255?state.selectedCode:code);draw();updateCoverage();scheduleSave();});
  byId('primary-assessment').addEventListener('change',event=>{currentAttempt().primaryAssessment=event.target.value;startAttempt();updateReadiness();scheduleSave();});byId('confidence').addEventListener('change',event=>{currentAttempt().confidence=event.target.value;startAttempt();updateReadiness();scheduleSave();});byId('notes').addEventListener('input',event=>{currentAttempt().notes=event.target.value.slice(0,1000);startAttempt();updateReadiness();scheduleSave();});document.querySelectorAll('#ambiguity input').forEach(input=>input.addEventListener('change',()=>{currentAttempt().ambiguity=Array.from(document.querySelectorAll('#ambiguity input:checked')).map(item=>item.value);startAttempt();updateReadiness();scheduleSave();}));
  byId('lock-attempt').addEventListener('click',lockAttempt);byId('confirm-lock').addEventListener('click',confirmLock);byId('reveal-answer').addEventListener('click',revealAnswer);byId('export-draft').addEventListener('click',exportDraft);byId('export-json').addEventListener('click',exportPracticeJson);byId('export-csv').addEventListener('click',exportPracticeCsv);
  byId('import-draft').addEventListener('change',event=>{const file=event.target.files&&event.target.files[0];if(!file)return;const reader=new FileReader();reader.onload=()=>{try{applyDraft(JSON.parse(String(reader.result)));saveLocal();}catch(error){showToast(error.message||'Invalid practice draft.',true);}event.target.value='';};reader.readAsText(file);});
  document.addEventListener('keydown',event=>{if(['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName))return;if(event.ctrlKey&&event.key.toLowerCase()==='z'){event.preventDefault();undo();return;}if(event.ctrlKey&&event.key.toLowerCase()==='y'){event.preventDefault();redo();return;}const map={'0':0,'1':1,'2':2,'3':3,'4':4,'u':255};const key=event.key.toLowerCase();if(Object.hasOwn(map,key)){state.selectedCode=map[key];renderPalette();}else if(key==='n'&&state.caseIndex<config.cases.length-1)switchCase(state.caseIndex+1);else if(key==='p'&&state.caseIndex>0)switchCase(state.caseIndex-1);});
  restoreLocal(); renderAll();
})();
"""
