"""Build the bounded MCP report artifact for a synthetic-practice audit."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


LABEL_NAMES = {
    0: "Dry land",
    1: "Temporary flood",
    2: "Permanent or pre-existing water",
    3: "Uncertain water change",
    4: "Unobservable or artifact",
}


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Build a validated-input report artifact from a practice audit."
    )
    parser.add_argument(
        "--assessment-directory",
        type=Path,
        required=True,
        help="Directory containing summary.json and the two audit CSV files.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        required=True,
        help="New report artifact JSON path.",
    )
    parser.add_argument(
        "--generated-at-utc",
        required=True,
        help="Timezone-aware ISO-8601 generation timestamp, normally ending in Z.",
    )
    return parser.parse_args()


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _as_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def _class_metrics(confusion_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    counts = {
        (int(row["truth_label_code"]), int(row["predicted_label_code"])): int(
            row["cell_count"]
        )
        for row in confusion_rows
    }
    output: list[dict[str, Any]] = []
    for code, class_name in LABEL_NAMES.items():
        truth_cells = sum(counts.get((code, predicted), 0) for predicted in LABEL_NAMES)
        predicted_cells = sum(counts.get((truth, code), 0) for truth in LABEL_NAMES)
        true_positive = counts.get((code, code), 0)
        precision = true_positive / predicted_cells if predicted_cells else None
        recall = true_positive / truth_cells if truth_cells else None
        denominator = truth_cells + predicted_cells
        dice = 2 * true_positive / denominator if denominator else None
        union = truth_cells + predicted_cells - true_positive
        iou = true_positive / union if union else None
        output.append(
            {
                "class_code": code,
                "class_name": class_name,
                "truth_cells": truth_cells,
                "predicted_cells": predicted_cells,
                "true_positive_cells": true_positive,
                "precision": precision,
                "recall": recall,
                "dice": dice,
                "iou": iou,
            }
        )
    return output


def _case_metrics(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        output.append(
            {
                "case_id": row["practice_case_id"],
                "teaching_challenge": row["teaching_challenge"],
                "selected_primary": row["selected_primary_assessment"],
                "expected_primary": row["expected_primary_assessment"],
                "primary_matches": _as_bool(row["primary_assessment_matches"]),
                "accuracy": float(row["accuracy"]),
                "temporary_flood_dice": float(row["temporary_flood_dice"]),
                "truth_flood_cells": int(row["truth_temporary_flood_cells"]),
                "predicted_flood_cells": int(row["predicted_temporary_flood_cells"]),
                "evidence_layers_viewed": int(row["evidence_layer_count"]),
                "all_layers_viewed": _as_bool(row["all_evidence_layers_viewed"]),
                "reasoning_note_present": _as_bool(row["reasoning_note_present"]),
                "confidence": row["confidence"],
                "duration_seconds": float(row["duration_seconds"]),
            }
        )
    return output


def build_artifact(
    assessment_directory: Path,
    generated_at_utc: str,
) -> dict[str, Any]:
    """Build a complete report manifest and bounded source snapshot."""

    summary = json.loads(
        (assessment_directory / "summary.json").read_text(encoding="utf-8")
    )
    if summary.get("validation_status") != "passed":
        raise ValueError("The practice audit must pass before report generation.")
    if summary.get("practice_only") is not True:
        raise ValueError("The report builder accepts practice-only audits only.")

    case_rows = _case_metrics(_load_csv(assessment_directory / "case_metrics.csv"))
    class_rows = _class_metrics(
        _load_csv(assessment_directory / "confusion_matrix.csv")
    )
    metrics = summary["summary_metrics"]
    heuristics = summary["practice_heuristics"]
    headline_rows = [
        {
            "integrity_issue_count": summary["integrity_issue_count"],
            "case_count": metrics["case_count"],
            "temporary_flood_dice": metrics["aggregate_temporary_flood_dice"],
            "temporary_flood_dice_practice_guide": heuristics["thresholds"][
                "minimum_aggregate_temporary_flood_dice"
            ],
            "reasoning_note_count": metrics["reasoning_note_present_count"],
            "reasoning_note_required_count": metrics["case_count"],
        }
    ]

    source = {
        "id": "src_practice_audit",
        "label": "Code-generated synthetic-practice audit",
        "path": (
            "human_coordination_v2/practice_attempts/practice_attempt_001/"
            "assessment_v1/summary.json"
        ),
        "query": {
            "engine": "duckdb",
            "language": "sql",
            "sql": (
                "SELECT 'summary' AS dataset_name, to_json(source_row) AS reviewed_row "
                "FROM read_json_auto('summary.json') AS source_row "
                "UNION ALL "
                "SELECT 'case_metrics' AS dataset_name, "
                "to_json(source_row) AS reviewed_row "
                "FROM read_csv_auto('case_metrics.csv', header = true) AS source_row "
                "UNION ALL "
                "SELECT 'confusion_matrix' AS dataset_name, "
                "to_json(source_row) AS reviewed_row "
                "FROM read_csv_auto('confusion_matrix.csv', header = true) AS source_row;"
            ),
            "description": (
                "Read the complete governed audit rows used by the Python report "
                "builder for headline, class, and case-level derivations. Run from "
                "the assessment_v1 directory."
            ),
            "executed_at": summary["audited_at_utc"],
            "tables_used": [
                "assessment_v1.summary.json",
                "assessment_v1.case_metrics.csv",
                "assessment_v1.confusion_matrix.csv",
            ],
            "filters": [
                "Synthetic teaching cases only",
                "Exactly 20 locked and revealed cases",
                "Exactly 1,024 classified cells per case",
                "No real event query or formal calibration evidence",
            ],
            "metric_definitions": [
                "Cell accuracy = correctly classified cells / all 20,480 cells.",
                (
                    "Temporary-flood Dice = 2 * flood true positives / "
                    "(2 * true positives + false positives + false negatives)."
                ),
                (
                    "Per-class Dice uses the same one-vs-rest calculation for "
                    "each of the five practice label codes."
                ),
                (
                    "Practice guide values are learning heuristics only and are "
                    "not formal reviewer-calibration thresholds."
                ),
            ],
        },
    }

    title = "Reviewer A Synthetic-Practice Assessment"
    manifest = {
        "version": 1,
        "surface": "report",
        "title": title,
        "description": (
            "Integrity result, learning diagnosis, and guarded next step for the "
            "first 20-case synthetic SAR practice attempt."
        ),
        "generatedAt": generated_at_utc,
        "sources": [source],
        "cards": [
            {
                "id": "card_integrity",
                "dataset": "headline_metrics",
                "sourceId": "src_practice_audit",
                "description": "Schema, checksum, timing, score, and safety checks.",
                "metrics": [
                    {
                        "label": "Integrity issues",
                        "field": "integrity_issue_count",
                        "format": "number",
                    }
                ],
            },
            {
                "id": "card_cases",
                "dataset": "headline_metrics",
                "sourceId": "src_practice_audit",
                "description": "Locked, revealed synthetic teaching cases audited.",
                "metrics": [
                    {
                        "label": "Complete cases",
                        "field": "case_count",
                        "format": "number",
                    }
                ],
            },
            {
                "id": "card_flood_dice",
                "dataset": "headline_metrics",
                "sourceId": "src_practice_audit",
                "description": (
                    "Pooled temporary-flood cell overlap; the comparison is a "
                    "practice guide, not a formal gate."
                ),
                "metrics": [
                    {
                        "label": "Temporary-flood Dice",
                        "field": "temporary_flood_dice",
                        "format": "percent",
                    },
                    {
                        "label": "Practice guide",
                        "field": "temporary_flood_dice_practice_guide",
                        "format": "percent",
                    },
                ],
            },
            {
                "id": "card_notes",
                "dataset": "headline_metrics",
                "sourceId": "src_practice_audit",
                "description": "Cases with a non-empty evidence-reasoning note.",
                "metrics": [
                    {
                        "label": "Notes completed",
                        "field": "reasoning_note_count",
                        "format": "number",
                    },
                    {
                        "label": "Required cases",
                        "field": "reasoning_note_required_count",
                        "format": "number",
                    },
                ],
            },
        ],
        "charts": [
            {
                "id": "chart_class_dice",
                "title": "Dice score by practice label class",
                "subtitle": (
                    "Uncertain water change and temporary flood have the weakest "
                    "one-vs-rest overlap."
                ),
                "intent": "comparison",
                "question": "Which label classes need the most remediation?",
                "rationale": (
                    "A horizontal bar comparison keeps the five long class names "
                    "readable and makes the weakest class overlap immediately visible."
                ),
                "type": "horizontalBar",
                "dataset": "class_metrics",
                "sourceId": "src_practice_audit",
                "encodings": {
                    "x": {
                        "field": "class_name",
                        "type": "nominal",
                        "label": "Practice label class",
                    },
                    "y": {
                        "field": "dice",
                        "type": "quantitative",
                        "format": "percent",
                        "label": "Dice score",
                    },
                    "tooltip": [
                        {"field": "truth_cells", "type": "quantitative"},
                        {"field": "predicted_cells", "type": "quantitative"},
                        {"field": "precision", "type": "quantitative", "format": "percent"},
                        {"field": "recall", "type": "quantitative", "format": "percent"},
                        {"field": "iou", "type": "quantitative", "format": "percent"},
                    ],
                },
                "valueFormat": "percent",
                "layout": "full",
                "maxRows": 5,
                "labels": {"values": "all"},
                "palette": {"kind": "sequential", "name": "teal"},
                "settings": {"sort": "ascending", "showValues": True},
                "surface": {"viewMode": "both", "showControls": True},
            }
        ],
        "tables": [
            {
                "id": "table_case_metrics",
                "title": "Case-level practice audit",
                "subtitle": "Lowest-accuracy cases appear first.",
                "dataset": "case_metrics",
                "sourceId": "src_practice_audit",
                "layout": "full",
                "density": "dense",
                "defaultSort": {"field": "accuracy", "direction": "asc"},
                "columns": [
                    {"field": "case_id", "label": "Case", "type": "text"},
                    {
                        "field": "teaching_challenge",
                        "label": "Teaching challenge",
                        "type": "text",
                    },
                    {
                        "field": "selected_primary",
                        "label": "Selected primary",
                        "type": "text",
                    },
                    {
                        "field": "expected_primary",
                        "label": "Expected primary",
                        "type": "text",
                    },
                    {
                        "field": "primary_matches",
                        "label": "Primary match",
                        "type": "text",
                    },
                    {
                        "field": "accuracy",
                        "label": "Cell accuracy",
                        "format": "percent",
                    },
                    {
                        "field": "temporary_flood_dice",
                        "label": "Flood Dice",
                        "format": "percent",
                    },
                    {
                        "field": "evidence_layers_viewed",
                        "label": "Layers viewed",
                        "format": "number",
                    },
                    {
                        "field": "reasoning_note_present",
                        "label": "Note present",
                        "type": "text",
                    },
                    {"field": "confidence", "label": "Confidence", "type": "text"},
                ],
            }
        ],
        "blocks": [
            {"id": "title", "type": "markdown", "body": f"# {title}"},
            {
                "id": "technical_summary",
                "type": "markdown",
                "sourceId": "src_practice_audit",
                "body": (
                    "## Technical Summary\n\n"
                    "The three exports are internally valid: all schema, checksum, "
                    "identity, timing, cell, score, and safety checks passed with "
                    "zero integrity issues across 20 cases and 20,480 cells. The "
                    "attempt is not yet learning-complete. Pooled temporary-flood "
                    "Dice is 49.4%, primary scenario match is 65%, only 9 of 20 "
                    "cases recorded all eight evidence layers, and no case contains "
                    "a reasoning note. The correct next status is "
                    "`first_pass_complete_needs_targeted_remediation`."
                ),
            },
            {
                "id": "headline_metrics",
                "type": "metric-strip",
                "cardIds": [
                    "card_integrity",
                    "card_cases",
                    "card_flood_dice",
                    "card_notes",
                ],
            },
            {
                "id": "scope_definitions",
                "type": "markdown",
                "sourceId": "src_practice_audit",
                "body": (
                    "## Scope and Metric Definitions\n\n"
                    "This assessment covers one blinded, synthetic, conceptual SAR "
                    "practice session. Cell accuracy is correct cells divided by all "
                    "20,480 cells. Dice is a class-overlap measure: 1.0 is exact "
                    "overlap and 0 is no overlap. The pooled temporary-flood Dice "
                    "combines all cells before calculation; this avoids the inflated "
                    "all-case macro average created when empty-empty flood cases "
                    "score 1.0. Practice guide values are learning heuristics only."
                ),
            },
            {
                "id": "class_finding",
                "type": "markdown",
                "sourceId": "src_practice_audit",
                "body": (
                    "## The Main Error Is Semantic Separation\n\n"
                    "The reviewer often found the changed region, but did not "
                    "consistently separate temporary flood from uncertain water "
                    "change. Uncertain cells were frequently painted dry or flood, "
                    "while true flood was sometimes painted uncertain. The chart "
                    "shows one-vs-rest class overlap; lower bars deserve more "
                    "practice, but sample size and class meaning must be considered."
                ),
            },
            {
                "id": "class_chart",
                "type": "chart",
                "chartId": "chart_class_dice",
                "layout": "full",
            },
            {
                "id": "case_finding",
                "type": "markdown",
                "sourceId": "src_practice_audit",
                "body": (
                    "## Where to Concentrate the Next Pass\n\n"
                    "The lowest-performing cases center on wet agricultural soil, "
                    "urban ambiguity, flooded vegetation, temporal mismatch, "
                    "misregistration, mixed boundaries, and permanent-water edges. "
                    "Use the table as a learning diagnostic, not a reviewer ranking. "
                    "The initial sort places the lowest cell accuracy first."
                ),
            },
            {
                "id": "case_table",
                "type": "table",
                "tableId": "table_case_metrics",
                "layout": "full",
            },
            {
                "id": "methodology",
                "type": "markdown",
                "sourceId": "src_practice_audit",
                "body": (
                    "## Methodology\n\n"
                    "A fail-closed auditor verified exact export schemas, workspace "
                    "and reviewer identity, 20 ordered cases, 1,024 unique cells per "
                    "case, allowed labels, locked/revealed state, cross-file "
                    "agreement, UTC timing, non-overlap, safety flags, source and "
                    "answer-key hashes, and independently recomputed scores. It "
                    "re-hashed inputs after analysis to detect mid-run changes and "
                    "then wrote self-hashed outputs atomically."
                ),
            },
            {
                "id": "limitations",
                "type": "markdown",
                "sourceId": "src_practice_audit",
                "body": (
                    "## Limitations and Robustness\n\n"
                    "These are synthetic teaching images, not real terrain-corrected "
                    "Sentinel-1 observations. Teaching answers are conceptual, not "
                    "expert-adjudicated event truth. Reveal timestamps and detailed "
                    "interaction history were not exported, so the audit cannot "
                    "independently prove how the answer was inspected. No evidence "
                    "of tampering was found. This report does not assess formal "
                    "calibration readiness, reviewer agreement, operational flood "
                    "detection, model quality, FPPS, or warning performance."
                ),
            },
            {
                "id": "next_step",
                "type": "markdown",
                "body": (
                    "## Next Step\n\n"
                    "Complete the fresh unseen 12-case synthetic remediation "
                    "workbench. On every case, explicitly visit all eight layers; "
                    "classify all 1,024 cells; make the primary assessment agree "
                    "with the grid; select confidence; add an ambiguity reason when "
                    "using class 3 or 4; and write at least 20 non-whitespace "
                    "reasoning characters. Export the draft, session JSON, and cell "
                    "CSV only after all 12 cases are locked and revealed. Formal "
                    "calibration and the 854 query cores remain held."
                ),
            },
            {
                "id": "further_questions",
                "type": "markdown",
                "body": (
                    "## Further Questions\n\n"
                    "After remediation: did flood-versus-uncertain Dice improve "
                    "without overusing dry land; were the five major SAR confounder "
                    "families distinguished; were all layers and notes completed; "
                    "and is another unseen practice pass needed before Phase 5 "
                    "read-only orientation?"
                ),
            },
        ],
    }

    snapshot = {
        "version": 1,
        "generatedAt": generated_at_utc,
        "status": "ready",
        "datasets": {
            "headline_metrics": headline_rows,
            "class_metrics": class_rows,
            "case_metrics": case_rows,
        },
    }
    return {
        "surface": "report",
        "manifest": manifest,
        "snapshot": snapshot,
        "sources": [source],
    }


def main() -> int:
    """Build and save the report artifact."""

    args = parse_args()
    assessment_directory = args.assessment_directory.resolve()
    output_json = args.output_json.resolve()
    if not assessment_directory.is_dir():
        raise FileNotFoundError(
            f"Assessment directory does not exist: {assessment_directory}"
        )
    if output_json.exists():
        raise FileExistsError(f"Refusing to overwrite artifact: {output_json}")
    output_json.parent.mkdir(parents=True, exist_ok=True)
    artifact = build_artifact(assessment_directory, args.generated_at_utc)
    output_json.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote report artifact: {output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
