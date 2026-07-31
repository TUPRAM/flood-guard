"""Build the technical MCP report for the Mae Sai real-data orientation."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from floodguard.label_factory.real_data_orientation import (  # noqa: E402
    verify_real_data_orientation_artifact,
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Build a technical report artifact from verified orientation data."
    )
    parser.add_argument(
        "--orientation-directory",
        type=Path,
        required=True,
        help="Verified aggregate real-data orientation directory.",
    )
    parser.add_argument(
        "--remediation-summary",
        type=Path,
        required=True,
        help="Final synthetic-remediation audit summary.json.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        required=True,
        help="New canonical report artifact path.",
    )
    parser.add_argument(
        "--generated-at-utc",
        required=True,
        help="Timezone-aware ISO-8601 generation timestamp, normally ending in Z.",
    )
    return parser.parse_args()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _numeric_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        converted: dict[str, Any] = {}
        for key, value in row.items():
            if value == "True":
                converted[key] = True
            elif value == "False":
                converted[key] = False
            else:
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    converted[key] = value
                else:
                    converted[key] = int(number) if number.is_integer() else number
        output.append(converted)
    return output


def build_artifact(
    orientation_directory: Path,
    remediation_summary_path: Path,
    generated_at_utc: str,
) -> dict[str, Any]:
    """Build the complete report manifest and bounded snapshot."""

    verify_real_data_orientation_artifact(orientation_directory)
    orientation = json.loads(
        (orientation_directory / "summary.json").read_text(encoding="utf-8")
    )
    remediation = json.loads(remediation_summary_path.read_text(encoding="utf-8"))
    if remediation.get("validation_status") != "passed":
        raise ValueError("The remediation audit must pass before report generation.")

    counts = orientation["counts"]
    safety = orientation["safety"]
    remediation_metrics = remediation["summary_metrics"]
    remediation_thresholds = remediation["practice_heuristics"]["thresholds"]

    histograms = _numeric_rows(
        _read_csv(orientation_directory / "change_histograms.csv")
    )
    histogram_totals: dict[str, int] = {}
    for row in histograms:
        feature = str(row["feature"])
        histogram_totals[feature] = histogram_totals.get(feature, 0) + int(
            row["cell_count"]
        )
    for row in histograms:
        row["bin_center"] = (float(row["bin_left"]) + float(row["bin_right"])) / 2
        row["cell_share"] = int(row["cell_count"]) / histogram_totals[
            str(row["feature"])
        ]

    context_rows = _numeric_rows(
        _read_csv(orientation_directory / "context_summary.csv")
    )
    sensitivity_rows = _numeric_rows(
        _read_csv(orientation_directory / "cluster_sensitivity.csv")
    )
    best_sensitivity = sorted(
        sensitivity_rows,
        key=lambda row: (-float(row["silhouette"]), int(row["k"])),
    )[0]
    selected_k = int(best_sensitivity["k"])
    cluster_rows = [
        row
        for row in _numeric_rows(
            _read_csv(orientation_directory / "cluster_summary.csv")
        )
        if int(row["k"]) == selected_k
    ]
    quantile_rows = _numeric_rows(
        _read_csv(orientation_directory / "feature_quantiles.csv")
    )

    headline_rows = [
        {
            "cell_count": int(counts["cell_count"]),
            "query_count": int(counts["query_count"]),
            "spatial_group_count": int(counts["spatial_group_count"]),
            "released_label_count": 0,
            "remediation_flood_dice": float(
                remediation_metrics["aggregate_temporary_flood_dice"]
            ),
            "remediation_flood_dice_guide": float(
                remediation_thresholds["minimum_aggregate_temporary_flood_dice"]
            ),
            "selected_k": selected_k,
            "best_silhouette": float(best_sensitivity["silhouette"]),
        }
    ]

    orientation_source = {
        "id": "src_real_orientation",
        "label": "Reviewer-safe Mae Sai real-data orientation",
        "path": "learning/real_data_orientation_v1/summary.json",
        "query": {
            "engine": "duckdb",
            "language": "sql",
            "sql": (
                "SELECT 'summary' AS dataset_name, to_json(source_row) AS reviewed_row "
                "FROM read_json_auto('summary.json') AS source_row UNION ALL "
                "SELECT 'change_histograms', to_json(source_row) "
                "FROM read_csv_auto('change_histograms.csv', header=true) AS source_row "
                "UNION ALL SELECT 'context_summary', to_json(source_row) "
                "FROM read_csv_auto('context_summary.csv', header=true) AS source_row "
                "UNION ALL SELECT 'cluster_sensitivity', to_json(source_row) "
                "FROM read_csv_auto('cluster_sensitivity.csv', header=true) AS source_row "
                "UNION ALL SELECT 'cluster_summary', to_json(source_row) "
                "FROM read_csv_auto('cluster_summary.csv', header=true) AS source_row;"
            ),
            "description": (
                "Read the verified aggregate-only orientation summary and reviewed "
                "distribution, context, and unsupervised-learning tables."
            ),
            "executed_at": orientation["created_at_utc"],
            "tables_used": [
                "real_data_orientation_v1.summary.json",
                "real_data_orientation_v1.change_histograms.csv",
                "real_data_orientation_v1.context_summary.csv",
                "real_data_orientation_v1.cluster_sensitivity.csv",
                "real_data_orientation_v1.cluster_summary.csv",
            ],
            "filters": [
                "Exposure lane reviewer_a_safe",
                "Aggregate outputs only",
                "No query ids, locations, weak overlap, labels, scores, or priority",
                "One Mae Sai event; 854 governed cores; 20 spatial groups",
            ],
            "metric_definitions": [
                "Cell count is the number of validated sar_change_v2 cell rows.",
                "Query count is the number of governed 32 by 32 cores.",
                "Context strata are static interpretation slices, not flood labels.",
                (
                    "Silhouette measures k-means compactness and separation on "
                    "standardized anonymous query aggregates; it is not accuracy."
                ),
            ],
        },
    }
    remediation_source = {
        "id": "src_remediation_audit",
        "label": "Synthetic remediation practice audit",
        "path": (
            "human_coordination_v2/practice_attempts/remediation_attempt_001/"
            "assessment_v2/summary.json"
        ),
        "query": {
            "engine": "duckdb",
            "language": "sql",
            "sql": "SELECT * FROM read_json_auto('summary.json');",
            "description": "Read the final governed 12-case remediation audit summary.",
            "executed_at": remediation["audited_at_utc"],
            "tables_used": ["remediation_attempt_001.assessment_v2.summary.json"],
            "filters": ["Synthetic remediation cases only", "Practice evidence only"],
            "metric_definitions": [
                (
                    "Pooled temporary-flood Dice combines all practice cells before "
                    "computing overlap; it is not a formal calibration metric."
                )
            ],
        },
    }

    title = "Mae Sai Real-Data and ML Learning Readiness"
    manifest: dict[str, Any] = {
        "version": 1,
        "surface": "report",
        "title": title,
        "description": (
            "Verified real-data orientation, unsupervised ML learning, and the "
            "honest gate before supervised flood modeling."
        ),
        "generatedAt": generated_at_utc,
        "sources": [orientation_source, remediation_source],
        "cards": [
            {
                "id": "card_cells",
                "dataset": "headline_metrics",
                "sourceId": "src_real_orientation",
                "description": "Validated, finite sar_change_v2 measurement rows.",
                "metrics": [
                    {"label": "Real SAR cells", "field": "cell_count", "format": "compact"}
                ],
            },
            {
                "id": "card_queries",
                "dataset": "headline_metrics",
                "sourceId": "src_real_orientation",
                "description": "Governed 32 by 32 query cores in the current event.",
                "metrics": [
                    {"label": "Query cores", "field": "query_count", "format": "number"},
                    {
                        "label": "Spatial groups",
                        "field": "spatial_group_count",
                        "format": "number",
                    },
                ],
            },
            {
                "id": "card_labels",
                "dataset": "headline_metrics",
                "sourceId": "src_real_orientation",
                "description": "Human labels that passed release QA, freeze, and revalidation.",
                "metrics": [
                    {
                        "label": "Released real labels",
                        "field": "released_label_count",
                        "format": "number",
                    }
                ],
            },
            {
                "id": "card_practice",
                "dataset": "headline_metrics",
                "sourceId": "src_remediation_audit",
                "description": (
                    "Synthetic learning result only; the guide is not a formal gate."
                ),
                "metrics": [
                    {
                        "label": "Practice flood Dice",
                        "field": "remediation_flood_dice",
                        "format": "percent",
                    },
                    {
                        "label": "Practice guide",
                        "field": "remediation_flood_dice_guide",
                        "format": "percent",
                    },
                ],
            },
        ],
        "charts": [
            {
                "id": "chart_change_histograms",
                "title": "VV and VH SAR-change distributions",
                "subtitle": "All 874,496 governed cells; positive pre minus event means darkening.",
                "intent": "comparison",
                "question": "How do VV and VH backscatter changes differ across the pool?",
                "rationale": (
                    "Two ordered distribution curves compare both polarizations on "
                    "the same dB change convention without implying flood truth."
                ),
                "type": "line",
                "dataset": "change_histograms",
                "sourceId": "src_real_orientation",
                "encodings": {
                    "x": {"field": "bin_center", "type": "quantitative", "label": "Change dB"},
                    "y": {
                        "field": "cell_share",
                        "type": "quantitative",
                        "format": "percent",
                        "label": "Cell share per bin",
                    },
                    "color": {"field": "feature", "type": "nominal", "label": "Polarization"},
                    "tooltip": [
                        {"field": "cell_count", "type": "quantitative"},
                        {"field": "bin_left", "type": "quantitative"},
                        {"field": "bin_right", "type": "quantitative"},
                    ],
                },
                "layout": "full",
                "maxRows": 100,
                "legend": {"position": "bottom", "title": "Change feature"},
                "palette": {"kind": "categorical"},
                "surface": {"viewMode": "both", "showControls": True},
            },
            {
                "id": "chart_context",
                "title": "Query count by static-context stratum",
                "subtitle": "Small water-edge and cropland slices remain descriptive only.",
                "intent": "comparison",
                "question": "Which static contexts dominate the governed query pool?",
                "rationale": "Horizontal bars keep the context labels readable and expose imbalance.",
                "type": "horizontalBar",
                "dataset": "context_summary",
                "sourceId": "src_real_orientation",
                "encodings": {
                    "x": {"field": "context_stratum", "type": "nominal", "label": "Context"},
                    "y": {"field": "query_count", "type": "quantitative", "label": "Queries"},
                    "tooltip": [
                        {"field": "spatial_group_count", "type": "quantitative"},
                        {"field": "mean_slope_p90_degrees", "type": "quantitative"},
                        {"field": "descriptive_only_small_slice", "type": "nominal"},
                    ],
                },
                "layout": "full",
                "maxRows": 20,
                "labels": {"values": "all"},
                "palette": {"kind": "sequential", "name": "teal"},
                "settings": {"sort": "ascending", "showValues": True},
                "surface": {"viewMode": "both", "showControls": True},
            },
            {
                "id": "chart_k_sensitivity",
                "title": "K-means sensitivity across candidate cluster counts",
                "subtitle": "Silhouette is pattern separation, not flood accuracy.",
                "intent": "comparison",
                "question": "How sensitive is the anonymous pattern grouping to k?",
                "rationale": "Four discrete candidate values are clearer as bars than as a trend.",
                "type": "bar",
                "dataset": "cluster_sensitivity",
                "sourceId": "src_real_orientation",
                "encodings": {
                    "x": {"field": "k_label", "type": "nominal", "label": "Cluster count"},
                    "y": {
                        "field": "silhouette",
                        "type": "quantitative",
                        "label": "Silhouette score",
                    },
                    "tooltip": [
                        {"field": "inertia", "type": "quantitative"},
                        {"field": "minimum_cluster_query_count", "type": "quantitative"},
                        {"field": "maximum_cluster_query_count", "type": "quantitative"},
                    ],
                },
                "layout": "full",
                "maxRows": 4,
                "labels": {"values": "all"},
                "palette": {"kind": "sequential", "name": "purple"},
                "settings": {"showValues": True},
                "surface": {"viewMode": "both", "showControls": True},
            },
        ],
        "tables": [
            {
                "id": "table_clusters",
                "title": "Selected anonymous pattern-cluster summary",
                "subtitle": f"k={selected_k}; centroids summarize query-level SAR change, not classes.",
                "dataset": "selected_clusters",
                "sourceId": "src_real_orientation",
                "layout": "full",
                "density": "spacious",
                "defaultSort": {"field": "query_count", "direction": "desc"},
                "columns": [
                    {"field": "cluster_id", "label": "Cluster", "format": "number"},
                    {"field": "query_count", "label": "Queries", "format": "number"},
                    {
                        "field": "centroid_mean_vv_change_db",
                        "label": "Mean VV change centroid",
                        "format": "number",
                    },
                    {
                        "field": "centroid_mean_vh_change_db",
                        "label": "Mean VH change centroid",
                        "format": "number",
                    },
                    {
                        "field": "centroid_std_vv_change_db",
                        "label": "VV variability centroid",
                        "format": "number",
                    },
                    {
                        "field": "centroid_std_vh_change_db",
                        "label": "VH variability centroid",
                        "format": "number",
                    },
                ],
            },
            {
                "id": "table_quantiles",
                "title": "Feature quantile audit",
                "subtitle": "Exact aggregate values for the seven sar_change_v2 features.",
                "dataset": "feature_quantiles",
                "sourceId": "src_real_orientation",
                "layout": "full",
                "density": "dense",
                "defaultSort": {"field": "feature", "direction": "asc"},
                "columns": [
                    {"field": "feature", "label": "Feature", "type": "text"},
                    {"field": "statistic", "label": "Statistic", "type": "text"},
                    {"field": "value", "label": "Value", "format": "number"},
                ],
            },
        ],
        "blocks": [
            {"id": "title", "type": "markdown", "body": f"# {title}"},
            {
                "id": "technical_summary",
                "type": "markdown",
                "sourceId": "src_real_orientation",
                "body": (
                    "## Technical Summary\n\n"
                    "The current Sep 3/Sep 15 Mae Sai Sentinel-1 lane is ready for "
                    "aggregate real-data analysis: 874,496 finite, formula-consistent "
                    "cells cover 854 governed cores and 20 spatial groups. The safe "
                    "orientation run found heterogeneous SAR-change and context "
                    "patterns and completed PCA/k-means learning without exposing "
                    "query identities. Supervised logistic/HGB training remains "
                    "correctly blocked because released real labels and a "
                    "release-bound training table do not exist."
                ),
            },
            {
                "id": "headline_metrics",
                "type": "metric-strip",
                "cardIds": ["card_cells", "card_queries", "card_labels", "card_practice"],
            },
            {
                "id": "practice_transition",
                "type": "markdown",
                "sourceId": "src_remediation_audit",
                "body": (
                    "## Practice Improved, but One Urban Case Remains Open\n\n"
                    "The 12-case remediation export passed every integrity check. "
                    "Pooled practice flood Dice improved from 49.4% to 71.6%, and "
                    "all eight layers plus reasoning notes were completed on every "
                    "case. The 75% learning guide was narrowly missed and one "
                    "supported urban-flood case had zero flood Dice. That supports "
                    "moving to reviewer-safe real orientation while retaining "
                    "targeted urban-SAR practice; it does not establish formal "
                    "calibration."
                ),
            },
            {
                "id": "scope_definitions",
                "type": "markdown",
                "sourceId": "src_real_orientation",
                "body": (
                    "## Measurements, Grain, and Exposure Boundary\n\n"
                    "One source row is one governed 10 m-grid cell. A 32 by 32 core "
                    "contains 1,024 correlated cells, so the future validation unit "
                    "is a spatial group rather than a random cell. VV/VH change is "
                    "pre-event minus event-time backscatter: positive means "
                    "darkening and negative means brightening. Neither sign is a "
                    "flood label. The `reviewer_a_safe` lane exposes only aggregates "
                    "and anonymized patterns; it hides query identities, weak overlap, "
                    "scores, and priorities."
                ),
            },
            {
                "id": "change_finding",
                "type": "markdown",
                "sourceId": "src_real_orientation",
                "body": (
                    "## Both Darkening and Brightening Are Common Real Signals\n\n"
                    "The two distributions straddle zero and have substantial tails. "
                    "Darkening can be compatible with smooth open water, while "
                    "brightening can occur with flooded vegetation or urban "
                    "double-bounce. Terrain, wet soil, agriculture, speckle, and "
                    "registration boundaries provide non-flood alternatives. Read "
                    "the curves as measured change, not flood probability."
                ),
            },
            {"id": "change_chart", "type": "chart", "chartId": "chart_change_histograms", "layout": "full"},
            {
                "id": "context_finding",
                "type": "markdown",
                "sourceId": "src_real_orientation",
                "body": (
                    "## Steep Terrain Dominates the Context Mix\n\n"
                    "The pool is not a balanced sample of Mae Sai surface types. "
                    "Steep-terrain context dominates, while permanent-water edge, "
                    "WorldCover-water edge, and cropland slices contain too few "
                    "queries or spatial groups for stable performance claims. Later "
                    "model evaluation must report denominators and groups per slice "
                    "instead of relying on one overall score."
                ),
            },
            {"id": "context_chart", "type": "chart", "chartId": "chart_context", "layout": "full"},
            {
                "id": "unsupervised_finding",
                "type": "markdown",
                "sourceId": "src_real_orientation",
                "body": (
                    "## Unsupervised ML Organizes Patterns, Not Truth\n\n"
                    "PCA summarizes correlated query-level backscatter features; "
                    "k-means groups similar standardized summaries. Silhouette "
                    "helps choose a descriptive k, but it measures cluster geometry "
                    "rather than flood correctness. Cluster IDs must remain anonymous "
                    "pattern labels and cannot become flood classes, probabilities, "
                    "or review priorities."
                ),
            },
            {"id": "sensitivity_chart", "type": "chart", "chartId": "chart_k_sensitivity", "layout": "full"},
            {"id": "cluster_table", "type": "table", "tableId": "table_clusters", "layout": "full"},
            {
                "id": "training_gate",
                "type": "markdown",
                "sourceId": "src_real_orientation",
                "body": (
                    "## The Supervised Training Gate Correctly Stops Here\n\n"
                    "The current pool has measurements but no released target. The "
                    "manual polygon is positive-unlabelled: its exterior is unknown, "
                    "not dry. Synthetic practice answers are also ineligible. A real "
                    "logistic/HGB committee requires a frozen labelset, passing "
                    "revalidation, and a release-bound training table with dry/flood "
                    "classes and spatial-group coverage. The current result is "
                    "`blocked_missing_released_training_labels`, which is a successful "
                    "fail-closed outcome."
                ),
            },
            {
                "id": "feature_audit",
                "type": "markdown",
                "sourceId": "src_real_orientation",
                "body": (
                    "## Feature Audit Detail\n\n"
                    "The table preserves exact aggregate values for the seven current "
                    "features. VV/VH changes are arithmetic functions of pre/event "
                    "values, and valid-data fraction is constant at one in the admitted "
                    "pool. Those dependencies matter when interpreting future logistic "
                    "coefficients or feature importance."
                ),
            },
            {"id": "quantile_table", "type": "table", "tableId": "table_quantiles", "layout": "full"},
            {
                "id": "methodology",
                "type": "markdown",
                "sourceId": "src_real_orientation",
                "body": (
                    "## Methodology and Robustness Checks\n\n"
                    "The builder rehashed and validated the feature derivation, "
                    "canonical query table, grid receipt, release seal, and context "
                    "join; processed the 628 MB feature pool in bounded chunks; "
                    "required exact row/query/group grain, finite features, formula "
                    "residuals within tolerance, and false downstream safety flags; "
                    "then standardized anonymous query aggregates for PCA and "
                    "deterministic k-means sensitivity at k=3 through 6. Outputs are "
                    "self-hashed, aggregate-only, and verified against forbidden "
                    "identity, weak-evidence, score, label, and priority fields."
                ),
            },
            {
                "id": "limitations",
                "type": "markdown",
                "sourceId": "src_real_orientation",
                "body": (
                    "## Limitations and Uncertainty\n\n"
                    "Only one event is represented. Registration passed the engineering "
                    "aggregate but is not independent geodetic truth. Static context is "
                    "not event-time flood evidence, and the strict JRC permanent-water "
                    "slice is especially sparse. Unsupervised clusters are sensitive to "
                    "feature scaling and k. No model accuracy, calibration, annotation "
                    "efficiency, event transfer, or geographic generalization claim is "
                    "possible from this run."
                ),
            },
            {
                "id": "next_steps",
                "type": "markdown",
                "body": (
                    "## Recommended Next Steps\n\n"
                    "1. Continue reviewer-safe full-scene interpretation and targeted "
                    "urban double-bounce versus supported-flood learning.\n"
                    "2. Keep the 854 formal cores unopened and all weak/model operator "
                    "evidence hidden if the proposed Reviewer A role is preserved.\n"
                    "3. Recruit and accept the Reference Authority, distinct Reviewer B, "
                    "and Adjudicator C; then complete genuine calibration and the first "
                    "20 formal cores under the governed procedure.\n"
                    "4. Unlock logistic/HGB only after consensus, release QA, freeze, "
                    "revalidation, and a release-bound training derivation.\n"
                    "5. Add at least one Thailand development event and preserve one "
                    "untouched geographic test before any generalization claim."
                ),
            },
            {
                "id": "further_questions",
                "type": "markdown",
                "body": (
                    "## Further Questions\n\n"
                    "Will the operator preserve the proposed Reviewer A role or later "
                    "switch explicitly to the ML-operator lane? Can a qualified "
                    "Reference Authority approve the real display and reference "
                    "procedure? Are the sparse JRC-water and cropland slices expected "
                    "from the source definitions, or do they need a documented context "
                    "sensitivity analysis before model use?"
                ),
            },
        ],
    }

    sensitivity_dataset = [
        {**row, "k_label": f"k={int(row['k'])}"} for row in sensitivity_rows
    ]
    snapshot = {
        "version": 1,
        "generatedAt": generated_at_utc,
        "status": "ready",
        "datasets": {
            "headline_metrics": headline_rows,
            "change_histograms": histograms,
            "context_summary": context_rows,
            "cluster_sensitivity": sensitivity_dataset,
            "selected_clusters": cluster_rows,
            "feature_quantiles": quantile_rows,
        },
    }
    return {
        "surface": "report",
        "manifest": manifest,
        "snapshot": snapshot,
        "sources": [orientation_source, remediation_source],
    }


def main() -> int:
    """Build and save the report artifact."""

    args = parse_args()
    orientation_directory = args.orientation_directory.resolve()
    remediation_summary = args.remediation_summary.resolve()
    output_json = args.output_json.resolve()
    if not orientation_directory.is_dir():
        raise FileNotFoundError(
            f"Orientation directory does not exist: {orientation_directory}"
        )
    if not remediation_summary.is_file():
        raise FileNotFoundError(
            f"Remediation summary does not exist: {remediation_summary}"
        )
    if output_json.exists():
        raise FileExistsError(f"Refusing to overwrite report artifact: {output_json}")
    output_json.parent.mkdir(parents=True, exist_ok=True)
    artifact = build_artifact(
        orientation_directory,
        remediation_summary,
        args.generated_at_utc,
    )
    output_json.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote report artifact: {output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
