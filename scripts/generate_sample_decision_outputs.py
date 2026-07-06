"""Generate sample road-risk, access, equity, and GeoJSON outputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.access import calculate_access_loss  # noqa: E402
from floodguard.briefs import write_action_briefs  # noqa: E402
from floodguard.dashboard import write_static_dashboard  # noqa: E402
from floodguard.equity import compute_equity_gap, equity_input_from_access_loss  # noqa: E402
from floodguard.exports import write_priority_geojson, write_road_risk_geojson  # noqa: E402
from floodguard.road_risk import score_road_disruption  # noqa: E402
from floodguard.sar_baseline import (  # noqa: E402
    run_threshold_sar_baseline,
    validate_threshold_sar_baseline,
)
from floodguard.scenarios import (  # noqa: E402
    build_scenario_comparison,
    merge_scenario_comparison,
    run_access_scenario,
)
from floodguard.scoring import score_subdistricts  # noqa: E402
from floodguard.sensitivity import run_weight_sensitivity, summarize_rank_instability  # noqa: E402
from floodguard.theos2_features import (  # noqa: E402
    write_theos2_landcover_exposure_features,
)
from floodguard.theos2_review import write_theos2_visual_review_checklist  # noqa: E402
from floodguard.validation import write_validation_summary  # noqa: E402


def main() -> None:
    """Generate all fixture-backed decision-layer sample outputs."""

    fixture_dir = REPO_ROOT / "tests" / "fixtures"
    output_dir = REPO_ROOT / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    roads = _geojson_properties(fixture_dir / "sample_roads.geojson")
    flood_probability = pd.read_csv(fixture_dir / "sample_flood_probability.csv")
    road_risk = score_road_disruption(roads, flood_probability)
    road_risk_path = output_dir / "sample_road_risk.csv"
    road_risk.to_csv(road_risk_path, index=False)

    access_loss = calculate_access_loss(
        population=pd.read_csv(fixture_dir / "sample_population_nodes.csv"),
        edges=pd.read_csv(fixture_dir / "sample_access_edges.csv"),
        facilities=pd.read_csv(fixture_dir / "sample_facilities.csv"),
    )
    access_loss_path = output_dir / "sample_access_loss.csv"
    access_loss.to_csv(access_loss_path, index=False)

    equity_input = equity_input_from_access_loss(access_loss, threshold=30)
    equity_gap = compute_equity_gap(equity_input)
    equity_gap_path = output_dir / "sample_equity_gap.csv"
    equity_gap.to_csv(equity_gap_path, index=False)

    priority = score_subdistricts(pd.read_csv(fixture_dir / "sample_population.csv"))
    priority_path = output_dir / "sample_priority_scores.csv"
    priority.loc[
        :,
        [
            "subdistrict_id",
            "subdistrict_name",
            "fpps_0_100",
            "action_class",
            "top_reason",
            "confidence_class",
            "source_name",
            "source_timestamp",
            "assumptions",
        ],
    ].to_csv(priority_path, index=False)

    population = pd.read_csv(fixture_dir / "sample_population_nodes.csv")
    edges = pd.read_csv(fixture_dir / "sample_access_edges.csv")
    facilities = pd.read_csv(fixture_dir / "sample_facilities.csv")
    scenario_summary_frames: list[pd.DataFrame] = []
    scenarios: dict[str, dict[str, pd.DataFrame]] = {}
    for scenario_name in ("add_temporary_shelter", "close_road"):
        scenario = run_access_scenario(
            population,
            edges,
            facilities,
            scenario_name,
            baseline_access=access_loss,
            baseline_equity=equity_gap,
        )
        scenario_access_path = output_dir / f"sample_scenario_{scenario_name}_access_loss.csv"
        scenario_equity_path = output_dir / f"sample_scenario_{scenario_name}_equity_gap.csv"
        scenario["access_loss"].to_csv(scenario_access_path, index=False)
        scenario["equity_gap"].to_csv(scenario_equity_path, index=False)
        scenario_summary_frames.append(scenario["scenario_summary"])
        scenarios[scenario_name] = scenario

    scenario_summary = pd.concat(scenario_summary_frames, ignore_index=True)
    scenario_summary_path = output_dir / "sample_scenario_summary.csv"
    scenario_summary.to_csv(scenario_summary_path, index=False)

    scenario_comparison = build_scenario_comparison(
        access_loss,
        equity_gap,
        scenarios["add_temporary_shelter"]["access_loss"],
        scenarios["add_temporary_shelter"]["equity_gap"],
        scenarios["close_road"]["access_loss"],
        scenarios["close_road"]["equity_gap"],
    )
    enriched_priority = merge_scenario_comparison(priority, scenario_comparison)

    priority_geojson_path = write_priority_geojson(
        fixture_dir / "sample_admin.geojson",
        enriched_priority,
        output_dir / "priority_subdistricts.geojson",
    )
    road_risk_geojson_path = write_road_risk_geojson(
        fixture_dir / "sample_roads.geojson",
        road_risk,
        output_dir / "road_risk.geojson",
    )

    sensitivity = run_weight_sensitivity(pd.read_csv(fixture_dir / "sample_population.csv"))
    sensitivity_path = output_dir / "sample_fpps_sensitivity.csv"
    sensitivity.to_csv(sensitivity_path, index=False)
    rank_instability = summarize_rank_instability(sensitivity)
    rank_instability_path = output_dir / "sample_fpps_rank_instability.csv"
    rank_instability.to_csv(rank_instability_path, index=False)

    sar_pixels = pd.read_csv(fixture_dir / "sample_sar_pixels.csv")
    sar_baseline = run_threshold_sar_baseline(sar_pixels)
    sar_baseline_path = output_dir / "sample_sar_baseline.csv"
    sar_baseline.to_csv(sar_baseline_path, index=False)
    sar_metrics = validate_threshold_sar_baseline(sar_pixels)
    sar_metrics_path = output_dir / "sample_sar_validation_metrics.csv"
    sar_metrics.to_csv(sar_metrics_path, index=False)

    validation_path = write_validation_summary(
        priority,
        road_risk,
        access_loss,
        equity_gap,
        output_dir / "validation_summary.md",
        rank_instability=rank_instability,
    )
    theos2_selected_path = _optional_path(output_dir / "theos2_selected_file_manifest.csv")
    theos2_thumbnail_path = _optional_path(output_dir / "theos2_thumbnail_manifest.csv")
    theos2_dashboard_manifest_path = theos2_thumbnail_path or theos2_selected_path
    theos2_context = _theos2_brief_context(theos2_selected_path, theos2_thumbnail_path)
    if theos2_selected_path is not None:
        theos2_feature_path = write_theos2_landcover_exposure_features(
            theos2_selected_path,
            output_dir / "theos2_landcover_exposure_features.csv",
        )
        theos2_review_path = write_theos2_visual_review_checklist(
            selected_manifest_path=theos2_selected_path,
            thumbnail_manifest_path=theos2_thumbnail_path,
            output_path=output_dir / "theos2_visual_review_checklist.csv",
        )
    else:
        theos2_feature_path = None
        theos2_review_path = None
    action_brief_paths = write_action_briefs(
        priority,
        road_risk,
        access_loss,
        equity_gap,
        output_dir,
        theos2_context=theos2_context,
    )
    dashboard_path = write_static_dashboard(
        priority_geojson_path,
        road_risk_geojson_path,
        validation_path,
        action_brief_paths,
        output_dir / "dashboard.html",
        theos2_preview_manifest_path=theos2_dashboard_manifest_path,
        local_library_manifest_path=output_dir / "local_data_library_manifest.csv",
        sentinel1_selected_manifest_path=output_dir / "sentinel1_selected_file_manifest.csv",
        sentinel1_provenance_manifest_path=output_dir / "sentinel1_provenance_resolved_manifest.csv",
        sentinel1_quicklook_manifest_path=output_dir / "sentinel1_quicklook_manifest.csv",
        dem_selected_manifest_path=output_dir / "dem_selected_file_manifest.csv",
        theos2_selected_manifest_path=theos2_selected_path,
        theos2_thumbnail_manifest_path=theos2_thumbnail_path,
    )

    print(f"Wrote {priority_path}")
    print(f"Wrote {road_risk_path}")
    print(f"Wrote {access_loss_path}")
    print(f"Wrote {equity_gap_path}")
    print(f"Wrote {priority_geojson_path}")
    print(f"Wrote {road_risk_geojson_path}")
    print(f"Wrote {validation_path}")
    if theos2_feature_path is not None:
        print(f"Wrote {theos2_feature_path}")
    if theos2_review_path is not None:
        print(f"Wrote {theos2_review_path}")
    for action_brief_path in action_brief_paths:
        print(f"Wrote {action_brief_path}")
    print(f"Wrote {dashboard_path}")
    print(f"Wrote {scenario_summary_path}")
    print(f"Wrote {sensitivity_path}")
    print(f"Wrote {rank_instability_path}")
    print(f"Wrote {sar_baseline_path}")
    print(f"Wrote {sar_metrics_path}")


def _geojson_properties(path: Path) -> pd.DataFrame:
    geojson = json.loads(path.read_text(encoding="utf-8"))
    return pd.DataFrame(
        [feature.get("properties", {}) for feature in geojson.get("features", [])]
    )


def _optional_path(path: Path) -> Path | None:
    return path if path.exists() else None


def _theos2_brief_context(
    selected_path: Path | None,
    thumbnail_path: Path | None,
) -> pd.DataFrame | None:
    if selected_path is None:
        return None
    selected = pd.read_csv(selected_path, dtype=str).fillna("")
    if thumbnail_path is None:
        return selected
    thumbnails = pd.read_csv(thumbnail_path, dtype=str).fillna("")
    if "thumbnail_path" not in thumbnails.columns:
        return selected
    thumbnail_paths = thumbnails.loc[:, ["file_name", "thumbnail_path"]].drop_duplicates(
        subset=["file_name"],
        keep="first",
    )
    merged = selected.merge(thumbnail_paths, on="file_name", how="left")
    has_thumbnail = merged["thumbnail_path"].astype(str).str.len() > 0
    merged.loc[has_thumbnail, "preview_path"] = merged.loc[has_thumbnail, "thumbnail_path"]
    return merged.drop(columns=["thumbnail_path"])


if __name__ == "__main__":
    main()
