"""Deterministic practice-only SAR remediation cases.

This package is a second synthetic teaching lane.  It deliberately targets
class confusions observed in the first conceptual practice pass, while staying
fully separate from reviewer calibration, formal labels, model training, and
FloodGuard decision outputs.  The learner-facing index contains only evidence
panels and case identifiers; teaching answers remain under ``answer_key`` for
the workbench's post-lock reveal step.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import html
import json
from pathlib import Path
from typing import Any

import numpy as np

from floodguard.label_factory.synthetic_learning import (
    SIZE,
    _binary_rgb,
    _canonical_hash,
    _change_rgb,
    _db_rgb,
    _label_rgb,
    _landcover_rgb,
    _sha256,
    _slope_rgb,
    _utc,
    _write_png,
)


SYNTHETIC_REMEDIATION_SCHEMA = "floodguard.synthetic_sar_remediation_cases.v1"
GENERATOR_VERSION = "synthetic_sar_remediation_v1"
CASE_IDS = tuple(f"SYN-REM-{index:03d}" for index in range(1, 13))
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
FALSE_SAFETY_FIELDS: tuple[str, ...] = (
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
EXPECTED_FOCUSES = (
    "flooded_vegetation_supported_flood",
    "flooded_vegetation_uncertain",
    "wet_soil_agricultural_uncertain",
    "temporal_mismatch_uncertain",
    "misregistration_artifact",
    "permanent_water_vs_artifact",
    "urban_ambiguity",
    "urban_double_bounce_supported_flood",
    "mixed_flood_boundary",
    "artifact_vs_dry",
    "permanent_water_plus_new_flood",
    "complete_multiclass",
)


class SyntheticRemediationError(ValueError):
    """Raised when a remediation package is unsafe or fails verification."""


@dataclass(frozen=True)
class RemediationCase:
    """One deterministic conceptual remediation exercise."""

    case_id: str
    remediation_focus: str
    challenge: str
    expected_primary: str
    rationale: str
    ambiguity_tags: tuple[str, ...]
    pre_vv: np.ndarray
    event_vv: np.ndarray
    pre_vh: np.ndarray
    event_vh: np.ndarray
    permanent_water: np.ndarray
    slope: np.ndarray
    landcover: np.ndarray
    labels: np.ndarray


def build_synthetic_remediation_package(
    output_directory: str | Path,
    *,
    created_at_utc: datetime,
) -> Path:
    """Write and verify 12 new, deterministic practice-only remediation cases."""

    created = _utc_for_remediation(created_at_utc)
    root = Path(output_directory)
    if root.exists() and any(root.iterdir()):
        raise SyntheticRemediationError(
            "Synthetic remediation output must be a new or empty directory."
        )
    root.mkdir(parents=True, exist_ok=True)
    answer_root = root / "answer_key"
    answer_root.mkdir()

    cases = tuple(_build_case(index) for index in range(1, 13))
    artifact_hashes: dict[str, str] = {}
    case_rows: list[dict[str, Any]] = []
    learner_cards: list[str] = []
    answer_cards: list[str] = []

    for case in cases:
        case_dir = root / case.case_id
        case_dir.mkdir()
        panels = {
            "pre_vv.png": _db_rgb(case.pre_vv),
            "event_vv.png": _db_rgb(case.event_vv),
            "pre_vh.png": _db_rgb(case.pre_vh),
            "event_vh.png": _db_rgb(case.event_vh),
            "vv_change.png": _change_rgb(case.pre_vv - case.event_vv),
            "permanent_water.png": _binary_rgb(
                case.permanent_water, (45, 133, 200)
            ),
            "slope.png": _slope_rgb(case.slope),
            "landcover.png": _landcover_rgb(case.landcover),
        }
        panel_hashes: dict[str, str] = {}
        for filename, values in panels.items():
            path = case_dir / filename
            _write_png(path, values)
            digest = _sha256(path)
            relative = path.relative_to(root).as_posix()
            artifact_hashes[relative] = digest
            panel_hashes[filename] = digest

        answer_path = answer_root / f"{case.case_id}_labels.png"
        _write_png(answer_path, _label_rgb(case.labels))
        answer_relative = answer_path.relative_to(root).as_posix()
        answer_digest = _sha256(answer_path)
        artifact_hashes[answer_relative] = answer_digest

        label_counts = {
            str(code): int(np.count_nonzero(case.labels == code))
            for code in (0, 1, 2, 3, 4, 255)
        }
        case_rows.append(
            {
                "case_id": case.case_id,
                "remediation_focus": case.remediation_focus,
                "challenge": case.challenge,
                "expected_primary": case.expected_primary,
                "ambiguity_tags": list(case.ambiguity_tags),
                "label_counts": label_counts,
                "rationale": case.rationale,
                "panel_sha256": panel_hashes,
                "answer_label_sha256": answer_digest,
            }
        )
        learner_cards.append(_learner_case_card(case.case_id))
        answer_cards.append(_answer_case_card(case))

    learner_index = root / "index.html"
    learner_index.write_text(
        _html_page(
            "FloodGuard synthetic remediation evidence",
            "".join(learner_cards),
            controlled_answers=False,
        ),
        encoding="utf-8",
        newline="\n",
    )
    artifact_hashes[learner_index.relative_to(root).as_posix()] = _sha256(
        learner_index
    )

    answer_index = answer_root / "index.html"
    answer_index.write_text(
        _html_page(
            "Controlled synthetic remediation answer key",
            "".join(answer_cards),
            controlled_answers=True,
        ),
        encoding="utf-8",
        newline="\n",
    )
    artifact_hashes[answer_index.relative_to(root).as_posix()] = _sha256(
        answer_index
    )

    readme = root / "README.md"
    readme.write_text(
        _readme_text(created.isoformat().replace("+00:00", "Z")),
        encoding="utf-8",
        newline="\n",
    )
    artifact_hashes[readme.relative_to(root).as_posix()] = _sha256(readme)

    values: dict[str, Any] = {
        "artifact_schema": SYNTHETIC_REMEDIATION_SCHEMA,
        "generator_version": GENERATOR_VERSION,
        "created_at_utc": created.isoformat().replace("+00:00", "Z"),
        "case_count": len(cases),
        "case_ids": [case.case_id for case in cases],
        "design_focus": list(EXPECTED_FOCUSES),
        "cases": case_rows,
        "artifact_sha256": dict(sorted(artifact_hashes.items())),
        "practice_only": True,
        "conceptual_teaching_only": True,
        "physical_sar_simulator": False,
        **{field: False for field in FALSE_SAFETY_FIELDS},
        "answers_separated_from_learner_index": True,
        "assumptions": (
            "Deterministic normalized teaching patterns with conceptual SAR-like "
            "responses. They are not calibrated Sentinel-1 measurements, formal "
            "reviewer calibration, reviewer-readiness evidence, or model evidence."
        ),
    }
    values["manifest_sha256"] = _canonical_hash(values)
    manifest = root / "manifest.json"
    manifest.write_text(
        json.dumps(values, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    verify_synthetic_remediation_package(root)
    return manifest


def verify_synthetic_remediation_package(output_directory: str | Path) -> None:
    """Verify schema, exact case coverage, safety, self-hash, and file hashes."""

    root = Path(output_directory)
    manifest_path = root / "manifest.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SyntheticRemediationError(
            f"Invalid synthetic remediation manifest: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise SyntheticRemediationError(
            "Synthetic remediation manifest must be a JSON object."
        )

    required = {
        "artifact_schema",
        "generator_version",
        "created_at_utc",
        "case_count",
        "case_ids",
        "design_focus",
        "cases",
        "artifact_sha256",
        "practice_only",
        "conceptual_teaching_only",
        "physical_sar_simulator",
        *FALSE_SAFETY_FIELDS,
        "answers_separated_from_learner_index",
        "assumptions",
        "manifest_sha256",
    }
    if set(payload) != required:
        raise SyntheticRemediationError(
            "Synthetic remediation manifest has unexpected keys."
        )
    if payload["artifact_schema"] != SYNTHETIC_REMEDIATION_SCHEMA:
        raise SyntheticRemediationError(
            "Synthetic remediation manifest schema is unsupported."
        )
    if payload["generator_version"] != GENERATOR_VERSION:
        raise SyntheticRemediationError(
            "Synthetic remediation generator version is unsupported."
        )
    if payload["case_count"] != 12 or payload["case_ids"] != list(CASE_IDS):
        raise SyntheticRemediationError(
            "Synthetic remediation package must contain the exact 12 ordered cases."
        )
    cases = payload["cases"]
    if not isinstance(cases, list) or len(cases) != 12:
        raise SyntheticRemediationError(
            "Synthetic remediation case rows are incomplete."
        )
    if [row.get("case_id") for row in cases if isinstance(row, dict)] != list(
        CASE_IDS
    ):
        raise SyntheticRemediationError(
            "Synthetic remediation case rows do not match the case ids."
        )
    if payload["design_focus"] != list(EXPECTED_FOCUSES):
        raise SyntheticRemediationError(
            "Synthetic remediation design focus is incomplete or reordered."
        )
    if payload["practice_only"] is not True:
        raise SyntheticRemediationError("Remediation package lost practice-only status.")
    if payload["conceptual_teaching_only"] is not True:
        raise SyntheticRemediationError(
            "Remediation package lost conceptual teaching-only status."
        )
    if payload["answers_separated_from_learner_index"] is not True:
        raise SyntheticRemediationError(
            "Remediation answer separation must remain explicit."
        )
    if payload["physical_sar_simulator"] is not False:
        raise SyntheticRemediationError(
            "Remediation package cannot claim to be a physical SAR simulator."
        )
    for field in FALSE_SAFETY_FIELDS:
        if payload[field] is not False:
            raise SyntheticRemediationError(
                f"Synthetic remediation package has unsafe {field}."
            )

    expected_case_keys = {
        "case_id",
        "remediation_focus",
        "challenge",
        "expected_primary",
        "ambiguity_tags",
        "label_counts",
        "rationale",
        "panel_sha256",
        "answer_label_sha256",
    }
    allowed_primary = {
        "0 dry",
        "1 temporary_flood",
        "2 permanent_water",
        "3 uncertain",
        "4 unobservable",
        "mixed_geometry",
    }
    hashes = payload["artifact_sha256"]
    if not isinstance(hashes, dict) or not hashes:
        raise SyntheticRemediationError(
            "Synthetic remediation artifact hashes are missing."
        )
    for index, row in enumerate(cases):
        if not isinstance(row, dict) or set(row) != expected_case_keys:
            raise SyntheticRemediationError(
                "Synthetic remediation case has unexpected fields."
            )
        case_id = CASE_IDS[index]
        if row["remediation_focus"] != EXPECTED_FOCUSES[index]:
            raise SyntheticRemediationError(
                f"Remediation focus does not match {case_id}."
            )
        if row["expected_primary"] not in allowed_primary:
            raise SyntheticRemediationError(
                f"Remediation case {case_id} has invalid expected primary."
            )
        for text_field in ("challenge", "rationale"):
            text = row[text_field]
            if not isinstance(text, str) or not text.strip() or len(text) > 1000:
                raise SyntheticRemediationError(
                    f"Remediation case {case_id} has invalid {text_field}."
                )
        tags = row["ambiguity_tags"]
        if not isinstance(tags, list) or not all(
            isinstance(tag, str) and tag.strip() and len(tag) <= 120 for tag in tags
        ):
            raise SyntheticRemediationError(
                f"Remediation case {case_id} has invalid ambiguity tags."
            )
        counts = row["label_counts"]
        if not isinstance(counts, dict) or set(counts) != {
            "0",
            "1",
            "2",
            "3",
            "4",
            "255",
        }:
            raise SyntheticRemediationError(
                f"Remediation case {case_id} has invalid label counts."
            )
        if sum(counts.values()) != SIZE * SIZE or counts["255"] != 0:
            raise SyntheticRemediationError(
                f"Remediation case {case_id} must cover all 1,024 cells."
            )
        panel_hashes = row["panel_sha256"]
        if not isinstance(panel_hashes, dict) or set(panel_hashes) != set(
            PANEL_FILES
        ):
            raise SyntheticRemediationError(
                f"Remediation case {case_id} has incomplete panel hashes."
            )
        for filename, digest in panel_hashes.items():
            relative = f"{case_id}/{filename}"
            if hashes.get(relative) != digest:
                raise SyntheticRemediationError(
                    f"Remediation case {case_id} panel hash linkage failed."
                )
        answer_relative = f"answer_key/{case_id}_labels.png"
        if hashes.get(answer_relative) != row["answer_label_sha256"]:
            raise SyntheticRemediationError(
                f"Remediation case {case_id} answer hash linkage failed."
            )

    for relative, expected in hashes.items():
        path = root / relative
        if not path.is_file() or _sha256(path) != expected:
            raise SyntheticRemediationError(
                f"Synthetic remediation artifact failed checksum: {relative}."
            )
    learner_index = (root / "index.html").read_text(encoding="utf-8")
    forbidden_learner_text = [
        *(row["challenge"] for row in cases),
        *(row["rationale"] for row in cases),
        *(row["expected_primary"] for row in cases),
        "answer_key",
    ]
    if any(text and text in learner_index for text in forbidden_learner_text):
        raise SyntheticRemediationError(
            "Learner index exposes controlled remediation answer content."
        )

    observed_hash = payload.pop("manifest_sha256")
    if observed_hash != _canonical_hash(payload):
        raise SyntheticRemediationError(
            "Synthetic remediation manifest self-hash does not match."
        )


def _build_case(index: int) -> RemediationCase:
    if index < 1 or index > 12:
        raise SyntheticRemediationError("Remediation case index must be 1 through 12.")
    rng = np.random.default_rng(30_000 + index)
    row, column = np.mgrid[0:SIZE, 0:SIZE]
    pre_vv = -10.0 + rng.normal(0, 0.55, (SIZE, SIZE))
    event_vv = pre_vv + rng.normal(0, 0.32, (SIZE, SIZE))
    pre_vh = -16.0 + rng.normal(0, 0.65, (SIZE, SIZE))
    event_vh = pre_vh + rng.normal(0, 0.38, (SIZE, SIZE))
    permanent = np.zeros((SIZE, SIZE), dtype=np.uint8)
    slope = np.clip(1.5 + row * 0.07 + rng.normal(0, 0.28, (SIZE, SIZE)), 0, 45)
    landcover = np.zeros((SIZE, SIZE), dtype=np.uint8)
    labels = np.zeros((SIZE, SIZE), dtype=np.uint8)

    focus = EXPECTED_FOCUSES[index - 1]
    challenge = ""
    expected_primary = ""
    rationale = ""
    tags: tuple[str, ...] = ()

    forest_patch = ((row - 15) / 7.0) ** 2 + ((column - 18) / 8.5) ** 2 <= 1
    field_patch = (row >= 8) & (row <= 25) & (column >= 6) & (column <= 26)
    river = np.abs(column - (11 + 1.8 * np.sin((row + 2) / 5))) <= 1
    shifted_river = np.abs(column - (14 + 1.8 * np.sin((row + 2) / 5))) <= 1
    core = (row - 17) ** 2 + (column - 15) ** 2 <= 6**2
    fringe = ((row - 17) ** 2 + (column - 15) ** 2 <= 9**2) & ~core

    if index == 1:
        challenge = "supported flooded-vegetation response"
        expected_primary = "1 temporary_flood"
        landcover[forest_patch] = 3
        event_vv[forest_patch] += 3.2
        event_vh[forest_patch] += 6.0
        labels[forest_patch] = 1
        rationale = (
            "A coherent vegetated patch brightens in both channels, with strong VH "
            "support. The conceptual reference treats it as flooded vegetation, not "
            "generic uncertainty."
        )
        tags = ("flooded_vegetation",)
    elif index == 2:
        challenge = "insufficient flooded-vegetation support"
        expected_primary = "3 uncertain"
        patch = forest_patch & (((row + column) % 5) != 0)
        landcover[forest_patch] = 3
        event_vv[patch] += 0.5
        event_vh[patch] += 2.1
        labels[patch] = 3
        rationale = (
            "Vegetation shows weak, polarization-asymmetric change. The conceptual "
            "evidence is observable but insufficient to call temporary flood."
        )
        tags = ("flooded_vegetation",)
    elif index == 3:
        challenge = "wet-soil agricultural change"
        expected_primary = "3 uncertain"
        patch = field_patch & (((row // 4 + column // 5) % 2) == 0)
        landcover[field_patch] = 2
        event_vv[patch] -= 2.8
        event_vh[patch] -= 0.7
        labels[patch] = 3
        rationale = (
            "Field-aligned VV darkening has weak VH support and may reflect wet soil "
            "or agricultural change. The flood meaning remains uncertain."
        )
        tags = ("wet_soil_or_agricultural_change",)
    elif index == 4:
        challenge = "temporally unresolved flood-compatible change"
        expected_primary = "3 uncertain"
        patch = ((row - 13) / 6.0) ** 2 + ((column - 19) / 8.0) ** 2 <= 1
        event_vv[patch] -= 5.0
        event_vh[patch] -= 1.0
        labels[patch] = 3
        rationale = (
            "The VV response is flood-compatible, but cross-polarization support is "
            "weak and target-time attribution is intentionally unresolved."
        )
        tags = ("temporal_mismatch",)
    elif index == 5:
        challenge = "pre/post misregistration edge"
        expected_primary = "4 unobservable"
        pre_feature = (row >= 6) & (row <= 25) & (column >= 10) & (column <= 14)
        event_feature = (row >= 6) & (row <= 25) & (column >= 12) & (column <= 16)
        pre_vv[pre_feature] += 7.0
        pre_vh[pre_feature] += 5.0
        event_vv[event_feature] += 7.0
        event_vh[event_feature] += 5.0
        artifact = np.logical_xor(pre_feature, event_feature)
        labels[artifact] = 4
        landcover[pre_feature | event_feature] = 1
        rationale = (
            "Paired edge responses arise from a shifted structured reflector. The "
            "affected cells are an alignment artifact, not uncertain flood water."
        )
        tags = ("pre_post_misregistration",)
    elif index == 6:
        challenge = "stable permanent water beside terrain artifact"
        expected_primary = "mixed_geometry"
        shadow = (row >= 20) & (column >= 21) & ((row + column) >= 48)
        for array, value in (
            (pre_vv, -22.0),
            (event_vv, -22.0),
            (pre_vh, -25.0),
            (event_vh, -25.0),
        ):
            array[river] = value + rng.normal(0, 0.3, int(river.sum()))
        pre_vv[shadow] = -26.0
        event_vv[shadow] = -26.0
        pre_vh[shadow] = -28.0
        event_vh[shadow] = -28.0
        permanent[river] = 1
        slope[shadow] = 36.0
        landcover[river] = 4
        labels[river] = 2
        labels[shadow & ~river] = 4
        rationale = (
            "Stable water confirmed by permanent-water context is code 2, while "
            "persistent darkness on steep unsupported terrain is code 4."
        )
        tags = ("permanent_water_boundary", "radar_shadow", "steep_terrain")
    elif index == 7:
        challenge = "urban layover and double-bounce ambiguity"
        expected_primary = "3 uncertain"
        urban = (row >= 7) & (row <= 25) & (column >= 5) & (column <= 26)
        patch = urban & (((row + 2 * column) % 4) != 0)
        landcover[urban] = 1
        pre_vv[urban] += 3.0
        pre_vh[urban] += 2.0
        event_vv[patch] += 2.2
        event_vh[patch] += 1.2
        labels[patch] = 3
        rationale = (
            "Structured urban brightening is visible, but the conceptual evidence "
            "cannot separate flood double-bounce from layover geometry."
        )
        tags = ("urban_double_bounce", "urban_layover")
    elif index == 8:
        challenge = "supported urban double-bounce flood"
        expected_primary = "1 temporary_flood"
        urban = (row >= 5) & (row <= 26) & (column >= 17) & (column <= 25)
        corridor = (row >= 9) & (row <= 23) & (column >= 12) & (column <= 18)
        landcover[urban] = 1
        pre_vv[urban] += 4.0
        pre_vh[urban] += 2.5
        event_vv[corridor] += 5.5
        event_vh[corridor] += 4.2
        labels[corridor] = 1
        rationale = (
            "A coherent corridor beside structured urban reflectors brightens strongly "
            "in both channels, supporting conceptual flood double-bounce."
        )
        tags = ("urban_double_bounce",)
    elif index == 9:
        challenge = "temporary-flood core with uncertain boundary"
        expected_primary = "mixed_geometry"
        event_vv[core] -= 7.0
        event_vh[core] -= 5.0
        event_vv[fringe] -= 2.2
        event_vh[fringe] -= 0.6
        labels[core] = 1
        labels[fringe] = 3
        rationale = (
            "The strongly supported central flood is code 1. The weak, inconsistent "
            "fringe remains code 3 instead of being forced into flood or dry."
        )
        tags = ("other",)
    elif index == 10:
        challenge = "terrain artifact versus stable dry land"
        expected_primary = "4 unobservable"
        shadow = (row >= 11) & (row <= 27) & (column >= 19) & (
            column <= row - 1
        )
        pre_vv[shadow] = -27.0
        event_vv[shadow] = -27.2
        pre_vh[shadow] = -29.0
        event_vh[shadow] = -28.8
        slope[shadow] = 40.0
        labels[shadow] = 4
        rationale = (
            "The rest of the scene is stable dry land. Persistent darkness coincident "
            "with steep terrain is unsupported observation and must be code 4."
        )
        tags = ("radar_shadow", "steep_terrain")
    elif index == 11:
        challenge = "permanent water plus adjacent new flood"
        expected_primary = "mixed_geometry"
        flood = shifted_river & ~river
        for array, value in (
            (pre_vv, -22.0),
            (event_vv, -22.0),
            (pre_vh, -25.0),
            (event_vh, -25.0),
        ):
            array[river] = value + rng.normal(0, 0.3, int(river.sum()))
        event_vv[flood] -= 7.0
        event_vh[flood] -= 5.0
        permanent[river] = 1
        landcover[river] = 4
        labels[river] = 2
        labels[flood] = 1
        rationale = (
            "The stable river remains code 2. Only the adjacent event-darkened cells "
            "are new temporary flood and receive code 1."
        )
        tags = ("permanent_water_boundary",)
    else:
        challenge = "complete five-class remediation geometry"
        expected_primary = "mixed_geometry"
        uncertain = (row <= 8) & (column <= 9)
        artifact = (row >= 24) & (column >= 22)
        flood = (row - 18) ** 2 + (column - 20) ** 2 <= 5**2
        flood &= ~river & ~artifact
        for array, value in (
            (pre_vv, -22.0),
            (event_vv, -22.0),
            (pre_vh, -25.0),
            (event_vh, -25.0),
        ):
            array[river] = value + rng.normal(0, 0.3, int(river.sum()))
        event_vv[flood] -= 7.0
        event_vh[flood] -= 5.0
        event_vv[uncertain] -= 2.4
        event_vh[uncertain] -= 0.5
        pre_vv[artifact] = -27.0
        event_vv[artifact] = -27.0
        pre_vh[artifact] = -29.0
        event_vh[artifact] = -29.0
        slope[artifact] = 39.0
        permanent[river] = 1
        landcover[river] = 4
        labels[river] = 2
        labels[flood] = 1
        labels[uncertain & ~river] = 3
        labels[artifact & ~river] = 4
        rationale = (
            "This case requires explicit dry, temporary flood, permanent water, "
            "uncertain change, and unsupported artifact without collapsing classes."
        )
        tags = ("permanent_water_boundary", "radar_shadow", "other")

    return RemediationCase(
        case_id=CASE_IDS[index - 1],
        remediation_focus=focus,
        challenge=challenge,
        expected_primary=expected_primary,
        rationale=rationale,
        ambiguity_tags=tags,
        pre_vv=pre_vv,
        event_vv=event_vv,
        pre_vh=pre_vh,
        event_vh=event_vh,
        permanent_water=permanent,
        slope=slope,
        landcover=landcover,
        labels=labels,
    )


def _learner_case_card(case_id: str) -> str:
    panels = "".join(
        f'<figure><img src="{case_id}/{name}" alt="{html.escape(case_id)} '
        f'{html.escape(name.removesuffix(".png").replace("_", " "))}">'
        f'<figcaption>{html.escape(name.removesuffix(".png").replace("_", " "))}'
        "</figcaption></figure>"
        for name in PANEL_FILES
    )
    return (
        f'<section class="case"><h2>{html.escape(case_id)}</h2>'
        '<p>Unseen synthetic remediation evidence. Record an answer before '
        "requesting controlled feedback.</p>"
        f'<div class="grid">{panels}</div></section>'
    )


def _answer_case_card(case: RemediationCase) -> str:
    tags = ", ".join(case.ambiguity_tags) if case.ambiguity_tags else "none"
    return (
        f'<section class="case"><h2>{html.escape(case.case_id)}</h2>'
        f'<p><strong>Focus:</strong> {html.escape(case.remediation_focus)}</p>'
        f'<p><strong>Challenge:</strong> {html.escape(case.challenge)}</p>'
        f'<p><strong>Expected primary:</strong> {html.escape(case.expected_primary)}</p>'
        f'<p><strong>Reasons:</strong> {html.escape(tags)}</p>'
        f'<p>{html.escape(case.rationale)}</p>'
        f'<img class="answer" src="{case.case_id}_labels.png" '
        f'alt="Controlled answer mask for {html.escape(case.case_id)}"></section>'
    )


def _html_page(title: str, body: str, *, controlled_answers: bool) -> str:
    warning = (
        "CONTROLLED ANSWERS - reveal only after an attempt is locked"
        if controlled_answers
        else "PRACTICE ONLY - answers are intentionally absent from this page"
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
body{{font-family:system-ui,sans-serif;margin:0;background:#101817;color:#eef7f4}}
header{{position:sticky;top:0;background:#7a3a00;padding:12px 20px;font-weight:800}}
main{{max-width:1200px;margin:auto;padding:22px}}.case{{background:#182422;border:1px solid #38514c;border-radius:12px;padding:18px;margin:0 0 18px}}
.grid{{display:grid;grid-template-columns:repeat(4,minmax(120px,1fr));gap:10px}}
figure{{margin:0;background:#09100f;padding:8px;border-radius:8px}}img{{width:100%;image-rendering:pixelated}}figcaption{{font-size:12px;margin-top:5px}}.answer{{max-width:420px}}
@media(max-width:760px){{.grid{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><header>{html.escape(warning)}</header>
<main><h1>{html.escape(title)}</h1>{body}</main></body></html>
"""


def _readme_text(created_at_utc: str) -> str:
    return f"""# FloodGuard synthetic SAR remediation cases

Created: `{created_at_utc}`

This directory contains 12 new deterministic 32 x 32 conceptual exercises
focused on class distinctions that can be difficult in SAR flood review. The
learner-facing `index.html` omits the teaching challenge, expected class,
rationale, ambiguity reasons, and answer mask. Controlled feedback lives under
`answer_key/` and should be revealed only after an attempt is locked.

The patterns are normalized teaching illustrations. They are not physical SAR
simulations, Sentinel-1 measurements, formal calibration queries, formal
reviewer-readiness evidence, training labels, evaluation labels, FPPS inputs,
or warning inputs.
"""


def _utc_for_remediation(value: datetime) -> datetime:
    try:
        return _utc(value)
    except (TypeError, ValueError) as exc:
        raise SyntheticRemediationError(str(exc)) from exc
