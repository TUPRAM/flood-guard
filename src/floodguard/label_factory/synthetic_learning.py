"""Deterministic conceptual SAR exercises for non-formal reviewer learning.

These images are teaching diagrams, not a Sentinel-1 simulator, flood truth,
reviewer calibration, model training data, or operational evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import struct
from typing import Any
import zlib

import numpy as np


SYNTHETIC_LEARNING_SCHEMA = "floodguard.synthetic_sar_learning_cases.v1"
GENERATOR_VERSION = "synthetic_sar_learning_v1"
SIZE = 32


class SyntheticLearningError(ValueError):
    """Raised when a synthetic learning package cannot be built safely."""


@dataclass(frozen=True, slots=True)
class SyntheticCase:
    """One deterministic conceptual SAR case and its hidden teaching answer."""

    case_id: str
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


def build_synthetic_learning_package(
    output_directory: str | Path,
    *,
    created_at_utc: datetime,
) -> Path:
    """Exclusively write 20 deterministic conceptual cases and a self-hash."""

    created = _utc(created_at_utc)
    root = Path(output_directory)
    if root.exists() and any(root.iterdir()):
        raise SyntheticLearningError(
            "Synthetic learning output must be a new or empty directory."
        )
    root.mkdir(parents=True, exist_ok=True)
    answer_root = root / "answer_key"
    answer_root.mkdir()

    cases = tuple(_build_case(index) for index in range(1, 21))
    artifact_hashes: dict[str, str] = {}
    case_rows: list[dict[str, Any]] = []
    index_cards: list[str] = []
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
            "permanent_water.png": _binary_rgb(case.permanent_water, (45, 133, 200)),
            "slope.png": _slope_rgb(case.slope),
            "landcover.png": _landcover_rgb(case.landcover),
        }
        for filename, values in panels.items():
            path = case_dir / filename
            _write_png(path, values)
            artifact_hashes[path.relative_to(root).as_posix()] = _sha256(path)

        answer_path = answer_root / f"{case.case_id}_labels.png"
        _write_png(answer_path, _label_rgb(case.labels))
        artifact_hashes[answer_path.relative_to(root).as_posix()] = _sha256(
            answer_path
        )
        label_counts = {
            str(code): int(np.count_nonzero(case.labels == code))
            for code in (0, 1, 2, 3, 4, 255)
        }
        case_rows.append(
            {
                "case_id": case.case_id,
                "challenge": case.challenge,
                "expected_primary": case.expected_primary,
                "ambiguity_tags": list(case.ambiguity_tags),
                "label_counts": label_counts,
                "rationale": case.rationale,
                "panel_sha256": {
                    name: artifact_hashes[f"{case.case_id}/{name}"]
                    for name in panels
                },
                "answer_label_sha256": artifact_hashes[
                    f"answer_key/{case.case_id}_labels.png"
                ],
            }
        )
        index_cards.append(_case_card(case))
        answer_cards.append(_answer_card(case))

    readme = _readme_text(created)
    readme_path = root / "README.md"
    readme_path.write_text(readme, encoding="utf-8", newline="\n")
    artifact_hashes[readme_path.relative_to(root).as_posix()] = _sha256(readme_path)

    index_path = root / "index.html"
    index_path.write_text(
        _html_page(
            "FloodGuard synthetic SAR learning cases",
            "".join(index_cards),
            answer_key=False,
        ),
        encoding="utf-8",
        newline="\n",
    )
    artifact_hashes[index_path.relative_to(root).as_posix()] = _sha256(index_path)

    answer_index = answer_root / "index.html"
    answer_index.write_text(
        _html_page(
            "FloodGuard synthetic SAR answer key",
            "".join(answer_cards),
            answer_key=True,
        ),
        encoding="utf-8",
        newline="\n",
    )
    artifact_hashes[answer_index.relative_to(root).as_posix()] = _sha256(answer_index)

    values: dict[str, Any] = {
        "artifact_schema": SYNTHETIC_LEARNING_SCHEMA,
        "generator_version": GENERATOR_VERSION,
        "created_at_utc": created.isoformat().replace("+00:00", "Z"),
        "case_count": len(cases),
        "case_ids": [case.case_id for case in cases],
        "cases": case_rows,
        "artifact_sha256": dict(sorted(artifact_hashes.items())),
        "conceptual_teaching_only": True,
        "physical_sar_simulator": False,
        "formal_reviewer_calibration": False,
        "real_event_queries_used": False,
        "eligible_for_query_model_training": False,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
        "assumptions": (
            "Conceptual, normalized teaching patterns with deterministic noise; "
            "not calibrated Sentinel-1 measurements or accuracy evidence."
        ),
    }
    values["manifest_sha256"] = _canonical_hash(values)
    manifest = root / "manifest.json"
    manifest.write_text(
        json.dumps(values, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    verify_synthetic_learning_package(root)
    return manifest


def verify_synthetic_learning_package(output_directory: str | Path) -> None:
    """Verify schema, self-hash, file hashes, case coverage, and safety flags."""

    root = Path(output_directory)
    manifest_path = root / "manifest.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SyntheticLearningError(f"Invalid synthetic manifest: {exc}") from exc
    required = {
        "artifact_schema",
        "generator_version",
        "created_at_utc",
        "case_count",
        "case_ids",
        "cases",
        "artifact_sha256",
        "conceptual_teaching_only",
        "physical_sar_simulator",
        "formal_reviewer_calibration",
        "real_event_queries_used",
        "eligible_for_query_model_training",
        "eligible_for_decision_layer",
        "eligible_for_fpps",
        "eligible_for_warning",
        "assumptions",
        "manifest_sha256",
    }
    if set(payload) != required:
        raise SyntheticLearningError("Synthetic manifest has unexpected keys.")
    if payload["artifact_schema"] != SYNTHETIC_LEARNING_SCHEMA:
        raise SyntheticLearningError("Synthetic manifest schema is unsupported.")
    if payload["generator_version"] != GENERATOR_VERSION:
        raise SyntheticLearningError("Synthetic generator version is unsupported.")
    if payload["case_count"] != 20 or len(payload["cases"]) != 20:
        raise SyntheticLearningError("Synthetic package must contain exactly 20 cases.")
    expected_ids = [f"SYN-SAR-{index:03d}" for index in range(1, 21)]
    if payload["case_ids"] != expected_ids:
        raise SyntheticLearningError("Synthetic case ids are incomplete or reordered.")
    if [row.get("case_id") for row in payload["cases"]] != expected_ids:
        raise SyntheticLearningError("Synthetic case rows do not match case ids.")
    if payload["conceptual_teaching_only"] is not True:
        raise SyntheticLearningError("Synthetic package lost its teaching-only status.")
    for field in (
        "physical_sar_simulator",
        "formal_reviewer_calibration",
        "real_event_queries_used",
        "eligible_for_query_model_training",
        "eligible_for_decision_layer",
        "eligible_for_fpps",
        "eligible_for_warning",
    ):
        if payload[field] is not False:
            raise SyntheticLearningError(f"Synthetic package has unsafe {field}.")
    hashes = payload["artifact_sha256"]
    if not isinstance(hashes, dict) or not hashes:
        raise SyntheticLearningError("Synthetic artifact hashes are missing.")
    for relative, expected in hashes.items():
        path = root / relative
        if not path.is_file() or _sha256(path) != expected:
            raise SyntheticLearningError(
                f"Synthetic artifact failed checksum: {relative}."
            )
    observed_hash = payload.pop("manifest_sha256")
    if observed_hash != _canonical_hash(payload):
        raise SyntheticLearningError("Synthetic manifest self-hash does not match.")


def _build_case(index: int) -> SyntheticCase:
    rng = np.random.default_rng(10_000 + index)
    row, column = np.mgrid[0:SIZE, 0:SIZE]
    pre_vv = -10.0 + rng.normal(0, 0.7, (SIZE, SIZE))
    event_vv = -10.0 + rng.normal(0, 0.7, (SIZE, SIZE))
    pre_vh = -16.0 + rng.normal(0, 0.8, (SIZE, SIZE))
    event_vh = -16.0 + rng.normal(0, 0.8, (SIZE, SIZE))
    permanent = np.zeros((SIZE, SIZE), dtype=np.uint8)
    slope = np.clip(2.0 + row * 0.08 + rng.normal(0, 0.35, (SIZE, SIZE)), 0, 45)
    landcover = np.zeros((SIZE, SIZE), dtype=np.uint8)
    labels = np.zeros((SIZE, SIZE), dtype=np.uint8)
    challenge = ""
    expected = ""
    rationale = ""
    tags: tuple[str, ...] = ()

    circle = (row - 17) ** 2 + (column - 16) ** 2 <= 7**2
    ellipse = ((row - 16) / 7.5) ** 2 + ((column - 17) / 10.0) ** 2 <= 1
    river = np.abs(column - (14 + 2 * np.sin(row / 4))) <= 2
    urban = (row >= 6) & (row <= 25) & (column >= 5) & (column <= 27)
    fields = ((row // 5 + column // 7) % 2) == 0
    forest = (row >= 5) & (row <= 27) & (column >= 8) & (column <= 25)

    if index == 1:
        challenge, expected = "clear open-water darkening", "1 temporary_flood"
        event_vv[circle] -= 8
        event_vh[circle] -= 6
        labels[circle] = 1
        rationale = "A coherent flat patch darkens strongly in both VV and VH and was not pre-existing water."
    elif index == 2:
        challenge, expected = "clear dry stable land", "0 dry"
        rationale = "Both dates and polarizations remain stable apart from deterministic speckle-like variation."
    elif index == 3:
        challenge, expected = "permanent-water edge", "2 permanent_water"
        for array, value in ((pre_vv, -22), (event_vv, -22), (pre_vh, -25), (event_vh, -25)):
            array[river] = value + rng.normal(0, 0.4, int(river.sum()))
        permanent[river] = 1
        landcover[river] = 4
        labels[river] = 2
        rationale = "The same dark river is present before and during the event and is confirmed by permanent-water context."
        tags = ("permanent_water_boundary",)
    elif index == 4:
        challenge, expected = "urban double-bounce", "1 temporary_flood"
        building = urban & (((row % 5) == 0) | ((column % 6) == 0))
        pre_vv[building], pre_vh[building] = -5, -11
        event_vv[building], event_vh[building] = -5, -11
        flood = urban & (row >= 14) & (row <= 22) & (column >= 10) & (column <= 24)
        event_vv[flood] += 5
        event_vh[flood] += 3
        landcover[urban] = 1
        labels[flood] = 1
        rationale = "Structured brightening beside urban reflectors is a conceptual double-bounce flood pattern, not open-water darkening."
        tags = ("urban_double_bounce",)
    elif index == 5:
        challenge, expected = "steep terrain and radar shadow", "4 unobservable"
        steep = column >= 18
        slope[steep] = 32 + (column[steep] - 18) * 1.2
        pre_vv[steep], event_vv[steep] = -24, -25
        pre_vh[steep], event_vh[steep] = -27, -27
        labels[steep] = 4
        rationale = "Persistent darkness coincides with very steep terrain; the ground is conceptually unsupported, not flood truth."
        tags = ("radar_shadow", "steep_terrain")
    elif index == 6:
        challenge, expected = "flooded vegetation brightening", "1 temporary_flood"
        landcover[forest] = 3
        pre_vv[forest], pre_vh[forest] = -12, -16
        flooded = forest & circle
        event_vv[flooded] = -7 + rng.normal(0, 0.5, int(flooded.sum()))
        event_vh[flooded] = -11 + rng.normal(0, 0.6, int(flooded.sum()))
        labels[flooded] = 1
        rationale = "A coherent forest patch brightens in both channels, illustrating flooded vegetation rather than smooth open water."
        tags = ("flooded_vegetation",)
    elif index == 7:
        challenge, expected = "wet soil or agricultural change", "3 uncertain"
        landcover[fields] = 2
        event_vv[fields] -= 3.2
        event_vh[fields] -= 1.0
        labels[fields] = 3
        rationale = "Field-shaped change with weak VH support could be rain, irrigation or management; the flood meaning is unresolved."
        tags = ("wet_soil_or_agricultural_change",)
    elif index == 8:
        challenge, expected = "speckle and isolated responses", "0 dry"
        points = ((row * 7 + column * 11 + 3) % 97) == 0
        event_vv[points] -= 10
        event_vh[points] += 5
        rationale = "Sparse incoherent outliers do not form a physically plausible flood patch."
        tags = ("speckle_or_isolated_response",)
    elif index == 9:
        challenge, expected = "pre/post misregistration edge", "4 unobservable"
        edge_pre = np.abs(column - 13) <= 1
        edge_event = np.abs(column - 15) <= 1
        pre_vv[edge_pre], pre_vh[edge_pre] = -4, -10
        event_vv[edge_event], event_vh[edge_event] = -4, -10
        affected = edge_pre | edge_event
        labels[affected] = 4
        rationale = "Opposite bright/dark edge pairs from a shifted linear feature are conceptual misregistration, not inundation."
        tags = ("pre_post_misregistration",)
    elif index == 10:
        challenge, expected = "temporal ambiguity", "3 uncertain"
        event_vv[ellipse] -= 6
        event_vh[ellipse] -= 4
        labels[ellipse] = 3
        rationale = "The radar change is flood-compatible, but the teaching scenario withholds evidence that it occurred at the target time."
        tags = ("temporal_mismatch",)
    elif index == 11:
        challenge, expected = "mixed flood/dry boundary", "mixed_geometry"
        event_vv[ellipse] -= 7
        event_vh[ellipse] -= 5
        labels[ellipse] = 1
        rationale = "Only the coherent ellipse is temporary flood; the observable stable exterior remains dry."
    elif index == 12:
        challenge, expected = "unobservable data support", "4 unobservable"
        unsupported = (column >= 13) & (column <= 18)
        for array in (pre_vv, event_vv, pre_vh, event_vh):
            array[unsupported] = np.nan
        labels[unsupported] = 4
        rationale = "The missing-data stripe is explicitly unobservable; it must not be filled as dry or flood."
    elif index == 13:
        challenge, expected = "complex open-water darkening", "1 temporary_flood"
        lobes = circle | (((row - 11) ** 2 + (column - 23) ** 2) <= 5**2)
        event_vv[lobes] -= 7.5
        event_vh[lobes] -= 5.5
        labels[lobes] = 1
        rationale = "Two connected coherent low-slope lobes darken in both polarizations without permanent-water support."
    elif index == 14:
        challenge, expected = "permanent water plus new flood", "mixed_geometry"
        for array, value in ((pre_vv, -22), (event_vv, -22), (pre_vh, -25), (event_vh, -25)):
            array[river] = value
        new_flood = (np.abs(column - (18 + 2 * np.sin(row / 4))) <= 3) & ~river
        event_vv[new_flood] -= 7
        event_vh[new_flood] -= 5
        permanent[river] = 1
        labels[river] = 2
        labels[new_flood] = 1
        rationale = "The pre-existing river stays code 2 while only the newly darkened adjacent area is code 1."
        tags = ("permanent_water_boundary",)
    elif index == 15:
        challenge, expected = "urban layover/double-bounce ambiguity", "3 uncertain"
        landcover[urban] = 1
        stripes = urban & (((row + column) % 5) == 0)
        pre_vv[stripes], event_vv[stripes] = -4, -2
        pre_vh[stripes], event_vh[stripes] = -10, -8
        labels[urban] = 3
        rationale = "Structured urban brightening is visible, but the conceptual evidence cannot separate flood double-bounce from geometry."
        tags = ("urban_double_bounce", "urban_layover")
    elif index == 16:
        challenge, expected = "flooded vegetation with mixed response", "1 temporary_flood"
        landcover[forest] = 3
        flooded = forest & (row >= 13) & (column <= 20)
        event_vv[flooded] += 2.5
        event_vh[flooded] += 5.0
        labels[flooded] = 1
        rationale = "Coherent VH-dominant brightening inside vegetation illustrates a flood pattern that a dark-only rule would miss."
        tags = ("flooded_vegetation",)
    elif index == 17:
        challenge, expected = "agricultural field change", "3 uncertain"
        landcover[fields] = 2
        changed = fields & (column >= 9)
        event_vv[changed] -= 4
        event_vh[changed] += 0.5
        labels[changed] = 3
        rationale = "Rectangular field changes without corroborating flood context remain uncertain rather than automatic flood."
        tags = ("wet_soil_or_agricultural_change",)
    elif index == 18:
        challenge, expected = "uncertain flood fringe", "mixed_geometry"
        core = ((row - 16) / 6) ** 2 + ((column - 16) / 8) ** 2 <= 1
        fringe = (((row - 16) / 9) ** 2 + ((column - 16) / 11) ** 2 <= 1) & ~core
        event_vv[core] -= 8
        event_vh[core] -= 6
        event_vv[fringe] -= 3
        event_vh[fringe] -= 1
        labels[core] = 1
        labels[fringe] = 3
        rationale = "Strong central evidence supports flood while a weaker fringe is preserved as uncertain instead of overdrawn."
    elif index == 19:
        challenge, expected = "multiple unresolved confounders", "3 uncertain"
        landcover[fields] = 2
        change = ellipse & fields
        event_vv[change] -= 4
        event_vh[change] -= 1
        slope[change] += 8
        labels[change] = 3
        rationale = "Agricultural pattern, moderate slope and asymmetric polarization support make the flood meaning unresolved."
        tags = ("wet_soil_or_agricultural_change", "steep_terrain")
    elif index == 20:
        challenge, expected = "complete multiclass geometry", "mixed_geometry"
        perm = river
        flood = (column >= 20) & circle & ~perm
        uncertain = (row <= 8) & (column <= 10)
        artifact = (row >= 25) & (column >= 24)
        event_vv[flood] -= 8
        event_vh[flood] -= 6
        for array, value in ((pre_vv, -22), (event_vv, -22), (pre_vh, -25), (event_vh, -25)):
            array[perm] = value
        event_vv[uncertain] -= 3
        labels[perm] = 2
        labels[flood] = 1
        labels[uncertain] = 3
        labels[artifact] = 4
        permanent[perm] = 1
        rationale = "The exercise requires explicit dry, temporary flood, permanent water, uncertain and artifact geometry without overlap."
        tags = ("permanent_water_boundary", "other")
    else:  # pragma: no cover - guarded by the caller's fixed range
        raise SyntheticLearningError(f"Unsupported synthetic case {index}.")

    return SyntheticCase(
        case_id=f"SYN-SAR-{index:03d}",
        challenge=challenge,
        expected_primary=expected,
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


def _case_card(case: SyntheticCase) -> str:
    panels = (
        ("Pre VV", "pre_vv.png"),
        ("Event VV", "event_vv.png"),
        ("Pre VH", "pre_vh.png"),
        ("Event VH", "event_vh.png"),
        ("VV change (pre - event)", "vv_change.png"),
        ("Permanent-water context", "permanent_water.png"),
        ("Slope context", "slope.png"),
        ("Land-cover context", "landcover.png"),
    )
    images = "".join(
        f'<figure><img src="{case.case_id}/{name}" alt="{html.escape(title)}">'
        f"<figcaption>{html.escape(title)}</figcaption></figure>"
        for title, name in panels
    )
    return (
        f'<section id="{case.case_id}"><h2>{case.case_id}</h2>'
        '<p class="prompt">Decide the supported class or mixed geometry before '
        "opening the separate answer key. Record confidence, time and reasoning.</p>"
        f'<div class="panels">{images}</div></section>'
    )


def _answer_card(case: SyntheticCase) -> str:
    tags = ", ".join(case.ambiguity_tags) if case.ambiguity_tags else "none"
    return (
        f'<section id="{case.case_id}"><h2>{case.case_id}: '
        f"{html.escape(case.challenge)}</h2>"
        f'<img class="answer" src="{case.case_id}_labels.png" alt="Expected label mask">'
        f"<p><strong>Expected primary:</strong> {html.escape(case.expected_primary)}</p>"
        f"<p><strong>Ambiguity tags:</strong> {html.escape(tags)}</p>"
        f"<p>{html.escape(case.rationale)}</p></section>"
    )


def _html_page(title: str, body: str, *, answer_key: bool) -> str:
    warning = (
        "Answer key: open only after locking your first attempt."
        if answer_key
        else "Conceptual teaching diagrams only. They are not real Sentinel-1 observations or formal calibration."
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>
body{{font-family:Arial,sans-serif;background:#081a2b;color:#e8eef5;margin:0;padding:24px}}
main{{max-width:1300px;margin:auto}}h1{{margin:0 0 8px}}.warning{{background:#4a2300;color:#ffe8b0;padding:12px;border-left:5px solid #f4b942}}
section{{background:#102b43;margin:22px 0;padding:18px;border-radius:10px}}.prompt{{color:#c9d8e6}}
.panels{{display:grid;grid-template-columns:repeat(4,minmax(180px,1fr));gap:12px}}figure{{margin:0;background:#07131e;padding:8px}}
img{{width:100%;image-rendering:pixelated;border:1px solid #50657a}}figcaption{{font-size:13px;margin-top:6px;color:#c9d8e6}}
.answer{{width:320px;max-width:100%;image-rendering:pixelated}}a{{color:#78c8ff}}strong{{color:#ffffff}}
@media(max-width:850px){{.panels{{grid-template-columns:repeat(2,minmax(130px,1fr))}}}}
</style></head><body><main><h1>{html.escape(title)}</h1><p class="warning">{html.escape(warning)}</p>{body}</main></body></html>
"""


def _readme_text(created: datetime) -> str:
    return f"""# Synthetic SAR learning cases v1

Created: {created.isoformat().replace('+00:00', 'Z')}

Open `index.html` and attempt each case before opening
`answer_key/index.html`. Record the result in the Phase 4 worksheet.

These deterministic 32 x 32 diagrams illustrate reasoning concepts only. They
are not a physical SAR simulator, real Sentinel-1 pixels, flood truth, formal
reviewer calibration, ML training data, FPPS input, or warning evidence.

Panel conventions:

- SAR panels: brighter gray means higher/less-negative conceptual dB return.
- VV change: red means positive `pre - event` (event became darker); blue means
  negative change (event became brighter).
- Permanent water: blue cells are conceptual historical-water context.
- Slope: brighter cells are conceptually steeper.
- Land cover: gray generic, red urban, tan agriculture, green forest, blue water.

The answer mask uses gray dry, blue temporary flood, cyan permanent water,
yellow uncertain, magenta unobservable/artifact, and black unreviewed.
"""


def _db_rgb(values: np.ndarray) -> np.ndarray:
    normalized = np.clip((values + 26.0) / 22.0, 0, 1)
    gray = np.where(np.isnan(values), 0, np.rint(normalized * 255)).astype(np.uint8)
    return np.repeat(gray[..., None], 3, axis=2)


def _change_rgb(values: np.ndarray) -> np.ndarray:
    valid = np.nan_to_num(values, nan=0.0)
    magnitude = np.clip(np.abs(valid) / 10.0, 0, 1)
    rgb = np.full((SIZE, SIZE, 3), 35, dtype=np.uint8)
    positive = valid >= 0
    rgb[..., 0] = np.where(positive, 35 + magnitude * 220, 35).astype(np.uint8)
    rgb[..., 2] = np.where(~positive, 35 + magnitude * 220, 35).astype(np.uint8)
    rgb[..., 1] = np.rint(35 + (1 - magnitude) * 45).astype(np.uint8)
    return rgb


def _binary_rgb(values: np.ndarray, color: tuple[int, int, int]) -> np.ndarray:
    rgb = np.full((SIZE, SIZE, 3), 25, dtype=np.uint8)
    rgb[values.astype(bool)] = color
    return rgb


def _slope_rgb(values: np.ndarray) -> np.ndarray:
    gray = np.rint(np.clip(values / 45.0, 0, 1) * 255).astype(np.uint8)
    return np.repeat(gray[..., None], 3, axis=2)


def _landcover_rgb(values: np.ndarray) -> np.ndarray:
    palette = np.array(
        [[100, 105, 110], [185, 65, 55], [194, 155, 83], [54, 128, 73], [55, 142, 204]],
        dtype=np.uint8,
    )
    return palette[values]


def _label_rgb(values: np.ndarray) -> np.ndarray:
    palette = {
        0: (120, 120, 120),
        1: (35, 113, 210),
        2: (55, 205, 218),
        3: (245, 194, 66),
        4: (202, 67, 196),
        255: (0, 0, 0),
    }
    rgb = np.zeros((SIZE, SIZE, 3), dtype=np.uint8)
    for code, color in palette.items():
        rgb[values == code] = color
    return rgb


def _write_png(path: Path, values: np.ndarray) -> None:
    if values.shape != (SIZE, SIZE, 3) or values.dtype != np.uint8:
        raise SyntheticLearningError("PNG values must be 32 x 32 uint8 RGB.")
    raw = b"".join(b"\x00" + values[row].tobytes() for row in range(SIZE))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    payload = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", SIZE, SIZE, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(payload)


def _canonical_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise SyntheticLearningError("created_at_utc must be timezone-aware.")
    return value.astimezone(timezone.utc)

