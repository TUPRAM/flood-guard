"""Build and execute the Reviewer A synthetic-practice audit notebook."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import nbformat
from nbclient import NotebookClient


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Build and execute a reproducible notebook from a successful "
            "FloodGuard synthetic-practice assessment."
        )
    )
    parser.add_argument(
        "--assessment-directory",
        type=Path,
        required=True,
        help="Directory containing summary.json and the two audit CSV files.",
    )
    parser.add_argument(
        "--output-notebook",
        type=Path,
        required=True,
        help="New .ipynb path to write.",
    )
    parser.add_argument(
        "--executed-at-utc",
        required=True,
        help="Timezone-aware ISO-8601 execution timestamp, normally ending in Z.",
    )
    return parser.parse_args()


def build_notebook() -> nbformat.NotebookNode:
    """Return the complete practice-audit notebook definition."""

    cells = [
        nbformat.v4.new_markdown_cell(
            """# Reviewer A synthetic-practice assessment

## Technical summary

This notebook independently reads the code-generated practice audit and explains
what the first synthetic attempt demonstrates. It is a learning report only. It
does **not** assess formal reviewer calibration, authorize formal Mae Sai query
access, create labels, train a model, affect FPPS, or support a warning claim.

**Answer first:** the exported files are internally valid and reproducible, but
the attempt needs targeted remediation before any later readiness discussion.
The main learning gap is separating temporary flood from uncertain water change,
especially around vegetation, agriculture, timing differences, registration
artifacts, and mixed boundaries.
"""
        ),
        nbformat.v4.new_markdown_cell(
            """## Context and method

The upstream auditor already performs strict schema, identity, timestamp,
cell-count, checksum, score, and safety-flag validation. This notebook consumes
only that governed output, re-checks its summary self-hash, derives class metrics
from the 5 × 5 confusion matrix, and ranks cases for learning follow-up.

To rerun this notebook, set `FLOODGUARD_PRACTICE_ASSESSMENT_DIR` to a successful
audit directory before starting the kernel. No personal filesystem path is
embedded in the notebook.
"""
        ),
        nbformat.v4.new_code_cell(
            """from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

assessment_dir = Path(os.environ["FLOODGUARD_PRACTICE_ASSESSMENT_DIR"])
executed_at_utc = os.environ["FLOODGUARD_NOTEBOOK_EXECUTED_AT_UTC"]

required_files = {
    "summary": assessment_dir / "summary.json",
    "case_metrics": assessment_dir / "case_metrics.csv",
    "confusion_matrix": assessment_dir / "confusion_matrix.csv",
}
missing = [str(path.name) for path in required_files.values() if not path.is_file()]
assert not missing, f"Missing governed audit files: {missing}"

summary = json.loads(required_files["summary"].read_text(encoding="utf-8"))
case_metrics = pd.read_csv(required_files["case_metrics"])
confusion = pd.read_csv(required_files["confusion_matrix"])

assert summary["validation_status"] == "passed"
assert summary["integrity_issue_count"] == 0
assert summary["practice_only"] is True
assert summary["formal_review_authorized"] is False
assert summary["eligible_for_reviewer_calibration"] is False
assert summary["eligible_for_query_model_training"] is False
assert summary["eligible_for_fpps"] is False
assert summary["eligible_for_warning"] is False
assert len(case_metrics) == summary["summary_metrics"]["case_count"]
assert int(confusion["cell_count"].sum()) == summary["summary_metrics"]["cell_count"]

print(f"Loaded governed assessment at {executed_at_utc}.")
print(f"Cases: {len(case_metrics):,}; cells: {int(confusion['cell_count'].sum()):,}.")
"""
        ),
        nbformat.v4.new_markdown_cell("## Data integrity and safety boundary"),
        nbformat.v4.new_code_cell(
            """hash_payload = dict(summary)
declared_summary_hash = hash_payload.pop("summary_sha256")
canonical = json.dumps(
    hash_payload,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")
recomputed_summary_hash = hashlib.sha256(canonical).hexdigest()
assert recomputed_summary_hash == declared_summary_hash

integrity_table = pd.DataFrame(
    [
        ("Audit validation", summary["validation_status"]),
        ("Integrity issues", summary["integrity_issue_count"]),
        ("Practice only", summary["practice_only"]),
        ("Real event queries used", summary["real_event_queries_used"]),
        ("Formal review authorized", summary["formal_review_authorized"]),
        ("Calibration eligibility", summary["eligible_for_reviewer_calibration"]),
        ("Model-training eligibility", summary["eligible_for_query_model_training"]),
        ("FPPS eligibility", summary["eligible_for_fpps"]),
        ("Warning eligibility", summary["eligible_for_warning"]),
        ("Summary self-hash", "verified"),
    ],
    columns=["check", "observed"],
)
integrity_table
"""
        ),
        nbformat.v4.new_markdown_cell("## Result overview"),
        nbformat.v4.new_code_cell(
            """metrics = summary["summary_metrics"]
overview = pd.DataFrame(
    [
        ("Cell accuracy", metrics["overall_accuracy"]),
        ("Temporary-flood precision", metrics["aggregate_temporary_flood_precision"]),
        ("Temporary-flood recall", metrics["aggregate_temporary_flood_recall"]),
        ("Temporary-flood Dice", metrics["aggregate_temporary_flood_dice"]),
        ("Flood-present case mean Dice", metrics["mean_flood_present_case_dice"]),
        ("Primary assessment match rate", metrics["primary_assessment_match_rate"]),
        ("All-eight-layers inspection rate", metrics["all_evidence_layers_viewed_case_count"] / metrics["case_count"]),
        ("Reasoning-note completion rate", metrics["reasoning_note_present_count"] / metrics["case_count"]),
    ],
    columns=["metric", "value"],
)
overview_display = overview.copy()
overview_display["value"] = overview_display["value"].map(lambda value: f"{value:.1%}")
overview_display
"""
        ),
        nbformat.v4.new_markdown_cell(
            """The overall cell accuracy is dominated by the large dry background.
Temporary-flood Dice, primary-assessment agreement, process completeness, and
class-specific confusions are more informative for the next learning decision.
"""
        ),
        nbformat.v4.new_code_cell(
            """label_order = (
    confusion[["truth_label_code", "truth_label_name"]]
    .drop_duplicates()
    .sort_values("truth_label_code")
)
class_rows = []
for row in label_order.itertuples(index=False):
    code = int(row.truth_label_code)
    name = str(row.truth_label_name)
    truth_total = int(confusion.loc[confusion.truth_label_code == code, "cell_count"].sum())
    predicted_total = int(confusion.loc[confusion.predicted_label_code == code, "cell_count"].sum())
    true_positive = int(
        confusion.loc[
            (confusion.truth_label_code == code)
            & (confusion.predicted_label_code == code),
            "cell_count",
        ].sum()
    )
    precision = true_positive / predicted_total if predicted_total else float("nan")
    recall = true_positive / truth_total if truth_total else float("nan")
    dice_denominator = truth_total + predicted_total
    dice = 2 * true_positive / dice_denominator if dice_denominator else float("nan")
    union = truth_total + predicted_total - true_positive
    iou = true_positive / union if union else float("nan")
    class_rows.append(
        {
            "label_code": code,
            "label_name": name,
            "truth_cells": truth_total,
            "predicted_cells": predicted_total,
            "precision": precision,
            "recall": recall,
            "dice": dice,
            "iou": iou,
        }
    )

class_metrics = pd.DataFrame(class_rows)
class_metrics_display = class_metrics.copy()
for metric_column in ["precision", "recall", "dice", "iou"]:
    class_metrics_display[metric_column] = class_metrics_display[metric_column].map(
        lambda value: f"{value:.1%}"
    )
class_metrics_display
"""
        ),
        nbformat.v4.new_code_cell(
            """plot_data = class_metrics.sort_values("dice")
fig, ax = plt.subplots(figsize=(9, 4.8))
bars = ax.barh(plot_data["label_name"], plot_data["dice"], color="#0f766e")
ax.set_xlim(0, 1)
ax.set_xlabel("Dice score")
ax.set_title("Class agreement: uncertainty and temporary flood need remediation")
ax.grid(axis="x", alpha=0.2)
for bar, value in zip(bars, plot_data["dice"], strict=True):
    ax.text(min(value + 0.02, 0.96), bar.get_y() + bar.get_height() / 2, f"{value:.1%}", va="center")
plt.tight_layout()
plt.show()
"""
        ),
        nbformat.v4.new_markdown_cell("## Case-level remediation priorities"),
        nbformat.v4.new_code_cell(
            """priority_columns = [
    "practice_case_id",
    "teaching_challenge",
    "selected_primary_assessment",
    "expected_primary_assessment",
    "primary_assessment_matches",
    "accuracy",
    "temporary_flood_dice",
    "evidence_layer_count",
    "reasoning_note_present",
    "confidence",
]
priority_cases = case_metrics.sort_values(
    ["accuracy", "temporary_flood_dice", "practice_case_id"]
)[priority_columns].head(10).copy()
priority_cases["accuracy"] = priority_cases["accuracy"].map(lambda value: f"{value:.1%}")
priority_cases["temporary_flood_dice"] = priority_cases["temporary_flood_dice"].map(
    lambda value: f"{value:.1%}"
)
priority_cases
"""
        ),
        nbformat.v4.new_code_cell(
            """off_diagonal = confusion.loc[
    confusion.truth_label_code != confusion.predicted_label_code
].sort_values("cell_count", ascending=False)
off_diagonal.head(10)
"""
        ),
        nbformat.v4.new_markdown_cell(
            """## Takeaways

1. **The files are trustworthy as practice exports.** All governed integrity,
   checksum, timing, identity, score, and safety checks passed with zero issues.
2. **The attempt is not yet learning-complete.** Temporary-flood Dice is about
   49%, primary-scenario match is 65%, only 9 of 20 cases recorded all eight
   evidence layers, and no case contains a reasoning note.
3. **The key problem is semantic, not merely geometric.** The largest errors
   exchange uncertain water change with dry land or temporary flood, and exchange
   temporary flood with uncertain water change. This supports a targeted
   remediation exercise rather than generic repetition.
4. **Do not use the macro all-case flood Dice as the headline.** Empty-truth and
   empty-prediction cases score 1.0 and inflate that mean. Pooled flood Dice and
   the mean across truth-flood cases are the safer learning indicators.
5. **No formal gate moved.** The correct status remains
   `first_pass_complete_needs_targeted_remediation`.

## Next step

Complete the fresh, unseen 12-case synthetic remediation workbench. For every
case, explicitly visit all eight layers, paint all 1,024 cells, record a
grid-consistent primary assessment, select confidence, add an ambiguity reason
when using class 3 or 4, and write at least 20 non-whitespace reasoning
characters. Export the draft, session JSON, and cell CSV only after all 12 cases
are locked and revealed.

## Further questions after remediation

- Did flood-versus-uncertain Dice improve without simply overusing dry land?
- Are flooded vegetation, agriculture, temporal mismatch, misregistration, and
  permanent-water boundaries now distinguished consistently?
- Did the reviewer use all evidence layers and written reasoning on every case?
- Is a second unseen practice pass needed before Phase 5 orientation?

Formal calibration remains out of scope until the distinct human roles,
Reference Authority approvals, genuine unseen reserve, expert/adjudicated
reference, and calibration procedure exist.
"""
        ),
    ]
    notebook = nbformat.v4.new_notebook(cells=cells)
    notebook.metadata["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    notebook.metadata["language_info"] = {"name": "python", "version": "3"}
    return notebook


def main() -> int:
    """Build, execute, and save the notebook."""

    args = parse_args()
    assessment_directory = args.assessment_directory.resolve()
    output_notebook = args.output_notebook.resolve()

    if not assessment_directory.is_dir():
        raise FileNotFoundError(
            f"Assessment directory does not exist: {assessment_directory}"
        )
    if output_notebook.suffix.lower() != ".ipynb":
        raise ValueError("--output-notebook must end in .ipynb")
    if output_notebook.exists():
        raise FileExistsError(f"Refusing to overwrite notebook: {output_notebook}")

    output_notebook.parent.mkdir(parents=True, exist_ok=True)
    notebook = build_notebook()

    previous_assessment = os.environ.get("FLOODGUARD_PRACTICE_ASSESSMENT_DIR")
    previous_execution = os.environ.get("FLOODGUARD_NOTEBOOK_EXECUTED_AT_UTC")
    os.environ["FLOODGUARD_PRACTICE_ASSESSMENT_DIR"] = str(assessment_directory)
    os.environ["FLOODGUARD_NOTEBOOK_EXECUTED_AT_UTC"] = args.executed_at_utc
    try:
        client = NotebookClient(
            notebook,
            timeout=180,
            kernel_name="python3",
            resources={"metadata": {"path": str(Path.cwd())}},
        )
        client.execute()
    finally:
        if previous_assessment is None:
            os.environ.pop("FLOODGUARD_PRACTICE_ASSESSMENT_DIR", None)
        else:
            os.environ["FLOODGUARD_PRACTICE_ASSESSMENT_DIR"] = previous_assessment
        if previous_execution is None:
            os.environ.pop("FLOODGUARD_NOTEBOOK_EXECUTED_AT_UTC", None)
        else:
            os.environ["FLOODGUARD_NOTEBOOK_EXECUTED_AT_UTC"] = previous_execution

    nbformat.write(notebook, output_notebook)
    print(f"Wrote executed notebook: {output_notebook}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
