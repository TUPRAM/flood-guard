"""Static dashboard writer for fixture-backed FloodGuard outputs."""

from __future__ import annotations

import csv
from collections.abc import Sequence
import html
import json
from pathlib import Path
from typing import Any

from floodguard.theos2_readiness import read_theos2_preview_rows


class DashboardError(ValueError):
    """Raised when dashboard inputs violate the dashboard contract."""


ActionBriefPaths = str | Path | Sequence[str | Path]


def write_static_dashboard(
    priority_geojson_path: str | Path,
    road_risk_geojson_path: str | Path,
    validation_summary_path: str | Path,
    action_brief_path: ActionBriefPaths,
    output_path: str | Path,
    theos2_preview_manifest_path: str | Path | None = None,
    local_library_manifest_path: str | Path | None = None,
    sentinel1_selected_manifest_path: str | Path | None = None,
    sentinel1_provenance_manifest_path: str | Path | None = None,
    sentinel1_quicklook_manifest_path: str | Path | None = None,
    dem_selected_manifest_path: str | Path | None = None,
    dem_quicklook_manifest_path: str | Path | None = None,
    theos2_selected_manifest_path: str | Path | None = None,
    theos2_thumbnail_manifest_path: str | Path | None = None,
) -> Path:
    """Write a standalone HTML dashboard with embedded GeoJSON and Markdown."""

    output_dir = Path(priority_geojson_path).parent
    priority_geojson = _read_feature_collection(priority_geojson_path, "priority")
    road_risk_geojson = _read_feature_collection(road_risk_geojson_path, "road_risk")
    validation_summary = Path(validation_summary_path).read_text(encoding="utf-8")
    action_briefs = _read_action_briefs(action_brief_path)
    theos2_preview_rows = read_theos2_preview_rows(theos2_preview_manifest_path)
    sentinel1_quicklook_rows = _read_sentinel1_quicklook_rows(
        output_dir,
        sentinel1_quicklook_manifest_path,
    )
    dem_quicklook_rows = _read_dem_quicklook_rows(output_dir, dem_quicklook_manifest_path)
    local_data_summary = _read_local_data_summary(
        output_dir=output_dir,
        local_library_manifest_path=local_library_manifest_path,
        sentinel1_selected_manifest_path=sentinel1_selected_manifest_path,
        sentinel1_provenance_manifest_path=sentinel1_provenance_manifest_path,
        sentinel1_quicklook_manifest_path=sentinel1_quicklook_manifest_path,
        dem_selected_manifest_path=dem_selected_manifest_path,
        dem_quicklook_manifest_path=dem_quicklook_manifest_path,
        theos2_selected_manifest_path=theos2_selected_manifest_path,
        theos2_thumbnail_manifest_path=theos2_thumbnail_manifest_path,
    )
    validation_metric_cards = _read_validation_metric_cards(output_dir)
    mae_sai_weak_summary = _read_mae_sai_weak_priority_summary(output_dir)

    top_priority = _select_top_actionable(priority_geojson)
    html_text = _build_dashboard_html(
        priority_geojson=priority_geojson,
        road_risk_geojson=road_risk_geojson,
        validation_summary=validation_summary,
        action_briefs=action_briefs,
        top_priority=top_priority,
        theos2_preview_rows=theos2_preview_rows,
        sentinel1_quicklook_rows=sentinel1_quicklook_rows,
        dem_quicklook_rows=dem_quicklook_rows,
        local_data_summary=local_data_summary,
        validation_metric_cards=validation_metric_cards,
        mae_sai_weak_summary=mae_sai_weak_summary,
    )

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html_text, encoding="utf-8")
    return target


def _read_feature_collection(path: str | Path, label: str) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("type") != "FeatureCollection":
        raise DashboardError(f"{label} GeoJSON must be a FeatureCollection.")
    if not isinstance(data.get("features"), list):
        raise DashboardError(f"{label} GeoJSON must include a features list.")
    return data


def _read_action_briefs(action_brief_paths: ActionBriefPaths) -> dict[str, str]:
    paths: list[Path]
    if isinstance(action_brief_paths, (str, Path)):
        paths = [Path(action_brief_paths)]
    else:
        paths = [Path(path) for path in action_brief_paths]
    if not paths:
        raise DashboardError("At least one action brief path is required.")

    briefs: dict[str, str] = {}
    prefix = "action_brief_"
    for path in paths:
        if not path.stem.startswith(prefix):
            raise DashboardError(
                f"Action brief filename must start with {prefix}: {path.name}"
            )
        subdistrict_id = path.stem.removeprefix(prefix)
        briefs[subdistrict_id] = path.read_text(encoding="utf-8")
    return briefs


def _read_sentinel1_quicklook_rows(
    output_dir: Path,
    sentinel1_quicklook_manifest_path: str | Path | None,
) -> list[dict[str, str]]:
    quicklook_path = _resolve_manifest_path(
        output_dir,
        sentinel1_quicklook_manifest_path,
        "sentinel1_quicklook_manifest.csv",
    )
    return _read_csv_rows(quicklook_path)


def _read_dem_quicklook_rows(
    output_dir: Path,
    dem_quicklook_manifest_path: str | Path | None,
) -> list[dict[str, str]]:
    quicklook_path = _resolve_manifest_path(
        output_dir,
        dem_quicklook_manifest_path,
        "dem_quicklook_manifest.csv",
    )
    return _read_csv_rows(quicklook_path)


def _read_local_data_summary(
    *,
    output_dir: Path,
    local_library_manifest_path: str | Path | None,
    sentinel1_selected_manifest_path: str | Path | None,
    sentinel1_provenance_manifest_path: str | Path | None,
    sentinel1_quicklook_manifest_path: str | Path | None,
    dem_selected_manifest_path: str | Path | None,
    dem_quicklook_manifest_path: str | Path | None,
    theos2_selected_manifest_path: str | Path | None,
    theos2_thumbnail_manifest_path: str | Path | None,
) -> dict[str, Any]:
    library_path = _resolve_manifest_path(
        output_dir,
        local_library_manifest_path,
        "local_data_library_manifest.csv",
    )
    sentinel_selected_path = _resolve_manifest_path(
        output_dir,
        sentinel1_selected_manifest_path,
        "sentinel1_selected_file_manifest.csv",
    )
    sentinel_provenance_path = _resolve_manifest_path(
        output_dir,
        sentinel1_provenance_manifest_path,
        "sentinel1_provenance_resolved_manifest.csv",
    )
    sentinel_quicklook_path = _resolve_manifest_path(
        output_dir,
        sentinel1_quicklook_manifest_path,
        "sentinel1_quicklook_manifest.csv",
    )
    dem_path = _resolve_manifest_path(
        output_dir,
        dem_selected_manifest_path,
        "dem_selected_file_manifest.csv",
    )
    dem_quicklook_path = _resolve_manifest_path(
        output_dir,
        dem_quicklook_manifest_path,
        "dem_quicklook_manifest.csv",
    )
    theos2_selected_path = _resolve_manifest_path(
        output_dir,
        theos2_selected_manifest_path,
        "theos2_selected_file_manifest.csv",
    )
    theos2_thumbnail_path = _resolve_manifest_path(
        output_dir,
        theos2_thumbnail_manifest_path,
        "theos2_thumbnail_manifest.csv",
    )

    library_rows = _read_csv_rows(library_path)
    sentinel_selected = _read_csv_rows(sentinel_selected_path)
    sentinel_provenance = _read_csv_rows(sentinel_provenance_path)
    sentinel_quicklooks = _read_csv_rows(sentinel_quicklook_path)
    dem_rows = _read_csv_rows(dem_path)
    dem_quicklooks = _read_csv_rows(dem_quicklook_path)
    theos2_selected = _read_csv_rows(theos2_selected_path)
    theos2_thumbnails = _read_csv_rows(theos2_thumbnail_path)
    library_counts = _counts_by_field(library_rows, "library_group")
    sentinel_ready = _first_row(sentinel_selected)
    sentinel_provenance_row = _first_row(sentinel_provenance)
    dem_package_count = len({row.get("package_name", "") for row in dem_rows if row.get("package_name")})

    return {
        "library_counts": {
            "sentinel1_sar": library_counts.get("sentinel1_sar", 0),
            "copernicus_dem": library_counts.get("copernicus_dem", 0),
            "theos2_optical": library_counts.get("theos2_optical", 0),
        },
        "sentinel1": {
            "file_name": sentinel_ready.get("file_name", "unavailable"),
            "mvp_overlap": sentinel_ready.get("mvp_overlap", "unavailable"),
            "band_descriptions": sentinel_ready.get("band_descriptions", "unavailable"),
            "sha256_status": sentinel_ready.get("sha256_status", "unavailable"),
            "candidate_role": sentinel_provenance_row.get("candidate_role", "unavailable"),
            "event_timing_status": sentinel_provenance_row.get("event_timing_status", "unavailable"),
            "provenance_status": sentinel_provenance_row.get("provenance_status", "unavailable"),
            "processing_allowed": sentinel_provenance_row.get(
                "processing_allowed",
                sentinel_ready.get("processing_allowed", "False"),
            ),
            "quicklook_count": len(sentinel_quicklooks),
            "blocked_reason": sentinel_provenance_row.get(
                "still_blocked_reason",
                sentinel_ready.get("reason_blocked", "unavailable"),
            ),
        },
        "dem": {
            "package_count": dem_package_count,
            "member_count": len(dem_rows),
            "quicklook_count": len(dem_quicklooks),
            "package_sha256_status": _common_status(dem_rows, "package_sha256_status"),
            "processing_scope": _common_status(dem_rows, "processing_scope"),
            "processing_allowed": _common_status(dem_rows, "processing_allowed"),
            "reference_mask_status": _common_status(dem_rows, "reference_mask_status"),
            "flood_observation_status": _common_status(dem_rows, "flood_observation_status"),
            "flood_label_status": _common_status(dem_rows, "flood_label_status"),
            "blocked_reason": _first_nonblank(dem_rows, "reason_blocked"),
        },
        "theos2": {
            "selected_count": len(theos2_selected),
            "thumbnail_count": len(theos2_thumbnails),
            "sha256_status": _common_status(theos2_selected, "sha256_status"),
            "processing_scope": _common_status(theos2_selected, "processing_scope"),
            "reference_mask_status": _common_status(theos2_selected, "reference_mask_status"),
            "processing_allowed": _common_status(theos2_selected, "processing_allowed"),
            "blocked_reason": (
                "optical context only; not flood validation or a reference mask"
                if theos2_selected
                else "THEOS-2 selected manifest unavailable"
            ),
        },
        "links": [
            {"label": "local_data_library_manifest.csv", "href": "local_data_library_manifest.csv"},
            {"label": "sentinel1_selected_file_manifest.csv", "href": "sentinel1_selected_file_manifest.csv"},
            {
                "label": "sentinel1_provenance_resolved_manifest.csv",
                "href": "sentinel1_provenance_resolved_manifest.csv",
            },
            {
                "label": "sentinel1_quicklook_manifest.csv",
                "href": "sentinel1_quicklook_manifest.csv",
            },
            {"label": "dem_selected_file_manifest.csv", "href": "dem_selected_file_manifest.csv"},
            {"label": "dem_quicklook_manifest.csv", "href": "dem_quicklook_manifest.csv"},
            {"label": "theos2_selected_file_manifest.csv", "href": "theos2_selected_file_manifest.csv"},
        ],
        "status_note": "Source files are outside Git and processing remains gated.",
    }


def _select_top_actionable(priority_geojson: dict[str, Any]) -> dict[str, Any]:
    action_order = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}
    features = priority_geojson.get("features", [])
    if not features:
        raise DashboardError("priority GeoJSON must include at least one feature.")

    def sort_key(feature: dict[str, Any]) -> tuple[int, float, str]:
        props = feature.get("properties") or {}
        action_class = str(props.get("action_class", "E"))
        if action_class not in action_order:
            raise DashboardError(f"Unknown action_class in priority GeoJSON: {action_class}")
        return (
            action_order[action_class],
            -float(props.get("fpps_0_100", 0)),
            str(props.get("subdistrict_id", "")),
        )

    return sorted(features, key=sort_key)[0]


def _build_dashboard_html(
    priority_geojson: dict[str, Any],
    road_risk_geojson: dict[str, Any],
    validation_summary: str,
    action_briefs: dict[str, str],
    top_priority: dict[str, Any],
    theos2_preview_rows: list[dict[str, str]],
    sentinel1_quicklook_rows: list[dict[str, str]],
    dem_quicklook_rows: list[dict[str, str]],
    local_data_summary: dict[str, Any],
    validation_metric_cards: list[dict[str, str]],
    mae_sai_weak_summary: dict[str, Any],
) -> str:
    props = top_priority.get("properties") or {}
    best_intervention = _scenario_summary(
        priority_geojson,
        "temporary_shelter_change_people_losing_30_min_access",
        prefer="min",
    )
    worst_road_closure = _scenario_summary(
        priority_geojson,
        "road_closure_change_people_losing_30_min_access",
        prefer="max",
    )
    template = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FloodGuard Static Dashboard</title>
  <link rel="icon" href="data:,">
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f8f4;
      --panel: #ffffff;
      --ink: #202722;
      --muted: #5b665f;
      --line: #d8ded4;
      --green: #21835f;
      --red: #b73c3c;
      --orange: #d36a35;
      --yellow: #d8a629;
      --violet: #6d5aa8;
      --neutral: #7f8a82;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Arial, Helvetica, sans-serif;
      line-height: 1.45;
    }
    .shell {
      min-height: 100vh;
      display: grid;
      grid-template-columns: minmax(340px, 410px) minmax(0, 1fr);
    }
    aside {
      background: var(--panel);
      border-right: 1px solid var(--line);
      padding: 20px;
      overflow-y: auto;
    }
    main {
      min-width: 0;
      display: grid;
      grid-template-rows: minmax(460px, 66vh) auto;
    }
    h1, h2, h3 {
      margin: 0;
      line-height: 1.15;
      letter-spacing: 0;
    }
    h1 { font-size: 23px; margin-bottom: 8px; }
    h2 { font-size: 15px; margin-top: 18px; margin-bottom: 10px; }
    h3 { font-size: 13px; margin-bottom: 8px; }
    p {
      margin: 0 0 12px;
      color: var(--muted);
      font-size: 14px;
    }
    label, select, input, button {
      font: inherit;
    }
    select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fbfcf8;
      color: var(--ink);
      padding: 8px 9px;
      min-height: 38px;
    }
    button {
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #eef2ed;
      color: var(--ink);
      cursor: pointer;
      min-height: 38px;
      padding: 8px 10px;
      text-align: center;
    }
    button:hover {
      background: #e3e9df;
    }
    .app-shell {
      display: flex;
      flex-direction: column;
      gap: 12px;
      padding: 14px 16px 0;
    }
    .app-header {
      display: grid;
      grid-template-columns: minmax(320px, 1fr) auto;
      align-items: center;
      gap: 16px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px 16px;
      box-shadow: 0 10px 26px rgba(32, 39, 34, .06);
    }
    .brand-row {
      display: flex;
      align-items: center;
      gap: 12px;
      min-width: 0;
    }
    .brand-mark {
      width: 42px;
      height: 42px;
      border-radius: 8px;
      display: grid;
      place-items: center;
      border: 2px solid #0f5f6d;
      color: #0f5f6d;
      font-weight: 800;
      font-size: 13px;
      background: #eef8f5;
      flex: 0 0 auto;
    }
    .brand-copy h1 {
      margin: 0 0 4px;
      font-size: 25px;
    }
    .brand-copy p {
      margin: 0;
      font-size: 13px;
    }
    .status-row {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 10px;
      flex-wrap: wrap;
      font-size: 12px;
    }
    .status-chip {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 7px 11px;
      background: #fbfcf8;
      font-weight: 700;
      white-space: nowrap;
    }
    .status-chip.demo { color: #255fb8; border-color: #9eb9ec; background: #f4f8ff; }
    .status-chip.warn { color: #9a5a00; border-color: #e1bd6b; background: #fff9e9; }
    .status-chip.blocked { color: #b73c3c; border-color: #e5a5a5; background: #fff4f4; }
    .timestamp {
      color: var(--muted);
      white-space: nowrap;
    }
    .kpi-strip {
      display: grid;
      grid-template-columns: repeat(8, minmax(112px, 1fr));
      gap: 10px;
    }
    .kpi-card {
      min-width: 0;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 11px;
      display: grid;
      gap: 4px;
      box-shadow: 0 8px 20px rgba(32, 39, 34, .04);
    }
    .kpi-card .label {
      margin: 0;
    }
    .kpi-card .value {
      font-size: 21px;
      line-height: 1.05;
    }
    .kpi-note {
      color: var(--muted);
      font-size: 11px;
      overflow-wrap: anywhere;
    }
    .dashboard-workspace {
      height: clamp(500px, calc(100vh - 390px), 540px);
      min-height: 500px;
      display: grid;
      grid-template-columns: minmax(250px, 280px) minmax(540px, 1fr) minmax(330px, 380px);
      gap: 14px;
      align-items: stretch;
    }
    .control-panel,
    .map-panel,
    .decision-panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 10px 26px rgba(32, 39, 34, .06);
      min-width: 0;
    }
    .control-panel {
      padding: 12px;
      overflow-y: auto;
      max-height: 100%;
    }
    .panel-title {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 12px;
    }
    .panel-title h2 {
      margin: 0;
      font-size: 16px;
    }
    .panel-title span {
      color: var(--muted);
      font-size: 11px;
      white-space: nowrap;
    }
    .map-panel {
      display: grid;
      grid-template-rows: auto minmax(0, 1fr);
      overflow: hidden;
      min-height: 500px;
    }
    .map-heading {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
    }
    .map-heading h2 {
      margin: 0;
      font-size: 16px;
    }
    .map-heading p {
      margin: 3px 0 0;
      font-size: 12px;
    }
    .map-body {
      position: relative;
      min-height: 0;
    }
    .map-legend {
      position: absolute;
      left: 14px;
      bottom: 14px;
      z-index: 480;
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 7px 16px;
      max-width: min(560px, calc(100% - 28px));
      padding: 10px;
      background: rgba(255, 255, 255, .94);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 12px 26px rgba(32, 39, 34, .12);
      font-size: 12px;
    }
    .legend-group {
      display: grid;
      gap: 6px;
    }
    .legend-group strong {
      font-size: 12px;
    }
    .legend-item {
      display: flex;
      align-items: center;
      gap: 7px;
      min-width: 0;
      color: var(--muted);
    }
    .road-sample {
      width: 24px;
      height: 0;
      border-top: 2px solid #b73c3c;
      flex: 0 0 auto;
    }
    .road-sample.medium { border-color: #d36a35; border-style: dashed; }
    .road-sample.low { border-color: #d8a629; border-style: dashed; }
    .road-sample.very-low { border-color: #7f8a82; border-style: dotted; }
    .leaflet-tooltip.subdistrict-label {
      background: transparent;
      border: 0;
      box-shadow: none;
      color: #101712;
      font-size: 10px;
      font-weight: 700;
      line-height: 1.08;
      text-align: center;
      text-shadow: 0 1px 2px rgba(255, 255, 255, .9);
      white-space: normal;
      width: 74px;
      pointer-events: none;
    }
    .leaflet-tooltip.subdistrict-label strong,
    .leaflet-tooltip.subdistrict-label span {
      display: block;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .leaflet-tooltip.subdistrict-label span {
      font-weight: 600;
    }
    .decision-panel {
      overflow-y: auto;
      max-height: 100%;
      padding: 0;
    }
    .panel-tabs {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      border-bottom: 1px solid var(--line);
      background: #fbfcf8;
      border-radius: 8px 8px 0 0;
    }
    .panel-tab {
      min-height: 42px;
      border: 0;
      border-right: 1px solid var(--line);
      border-radius: 0;
      background: transparent;
      font-size: 12px;
      color: var(--muted);
      font-weight: 700;
    }
    .panel-tab:last-child {
      border-right: 0;
    }
    .panel-tab.active {
      color: #255fb8;
      background: #ffffff;
      box-shadow: inset 0 -2px 0 #255fb8;
    }
    .panel-section {
      padding: 12px;
      border-bottom: 1px solid var(--line);
    }
    .panel-section:last-child {
      border-bottom: 0;
    }
    .brief-heading-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 10px;
    }
    .brief-heading-row strong {
      overflow-wrap: anywhere;
    }
    .class-pill {
      border-radius: 6px;
      padding: 5px 8px;
      background: #fff4f4;
      color: var(--red);
      border: 1px solid #e5a5a5;
      font-size: 12px;
      font-weight: 800;
      white-space: nowrap;
    }
    .compact-list {
      margin: 8px 0 0;
      padding-left: 18px;
      color: var(--muted);
      font-size: 12px;
    }
    .control-stack {
      display: grid;
      gap: 10px;
      margin: 14px 0;
    }
    .control-label {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 4px;
    }
    .filter-row {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 6px;
    }
    .filter-row label {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 4px;
      min-height: 34px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fbfcf8;
      font-size: 13px;
    }
    .button-row {
      display: grid;
      grid-template-columns: 1fr;
      gap: 8px;
      margin: 12px 0 4px;
    }
    .metric-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin: 14px 0;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      background: #fbfcf8;
      min-width: 0;
    }
    .summary-card-grid {
      display: grid;
      grid-template-columns: 1fr;
      gap: 8px;
      margin: 10px 0 14px;
    }
    .summary-card {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      background: #fbfcf8;
    }
    .summary-card strong {
      display: block;
      margin: 2px 0 4px;
      font-size: 15px;
      overflow-wrap: anywhere;
    }
    .summary-card span:last-child {
      color: var(--muted);
      font-size: 13px;
    }
    .mae-sai-weak-card {
      border: 1px solid #d6c48f;
      border-radius: 6px;
      background: #fffaf0;
      padding: 10px;
      display: grid;
      gap: 8px;
      margin: 10px 0 14px;
      font-size: 12px;
    }
    .mae-sai-weak-card strong {
      font-size: 13px;
      color: var(--ink);
    }
    .mae-sai-weak-card dl {
      display: grid;
      grid-template-columns: minmax(94px, auto) minmax(0, 1fr);
      gap: 4px 8px;
      margin: 0;
    }
    .mae-sai-weak-card dt {
      color: var(--muted);
    }
    .mae-sai-weak-card dd {
      margin: 0;
      overflow-wrap: anywhere;
    }
    .mae-sai-weak-card .warning {
      border-top: 1px solid #eadcb2;
      padding-top: 7px;
      color: #8b5b00;
    }
    .status-panel {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 12px;
      background: #fbfcf8;
      display: grid;
      gap: 10px;
      margin: 14px 0;
    }
    .status-panel > strong {
      font-size: 15px;
    }
    .status-panel p {
      margin: 0;
      font-size: 13px;
    }
    .status-grid {
      display: grid;
      grid-template-columns: 1fr;
      gap: 8px;
    }
    .status-item {
      border-top: 1px solid var(--line);
      padding-top: 8px;
      font-size: 13px;
    }
    .status-item strong {
      display: block;
      margin-bottom: 3px;
    }
    .boundary-list,
    .gate-list {
      margin: 4px 0 0;
      padding-left: 18px;
      color: var(--muted);
      font-size: 12px;
    }
    .boundary-list li,
    .gate-list li {
      margin: 2px 0;
    }
    .label {
      display: block;
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0;
      margin-bottom: 4px;
    }
    .value {
      display: block;
      font-size: 19px;
      font-weight: 700;
      overflow-wrap: anywhere;
    }
    .summary-list {
      padding: 0;
      margin: 0;
      list-style: none;
      display: grid;
      gap: 8px;
      font-size: 14px;
    }
    .summary-list li {
      border-top: 1px solid var(--line);
      padding-top: 8px;
    }
    .safety-note {
      margin-top: 10px;
      border: 1px solid #b8cdea;
      border-radius: 6px;
      background: #f4f8ff;
      color: #255fb8;
      padding: 8px 10px;
      font-size: 12px;
      line-height: 1.35;
    }
    .context-preview-heading {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 10px;
    }
    .context-preview-heading h2 {
      margin: 0;
    }
    .context-preview-heading span {
      color: var(--muted);
      font-size: 11px;
      white-space: nowrap;
    }
    .context-preview-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
    }
    .theos2-context,
    .sar-context,
    .dem-context {
      display: grid;
      gap: 8px;
      margin: 0;
    }
    .theos2-card,
    .sar-card,
    .dem-card {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 7px;
      background: #fbfcf8;
      display: grid;
      gap: 5px;
    }
    .theos2-card img,
    .sar-card img,
    .dem-card img {
      display: block;
      width: 100%;
      aspect-ratio: 1 / 1;
      max-height: 92px;
      object-fit: cover;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #f7f8f4;
    }
    .theos2-card strong,
    .sar-card strong,
    .dem-card strong {
      font-size: 11px;
      line-height: 1.2;
      overflow-wrap: anywhere;
    }
    .theos2-card span,
    .sar-card span,
    .dem-card span {
      color: var(--muted);
      font-size: 10px;
      line-height: 1.25;
      overflow-wrap: anywhere;
    }
    .sar-card:nth-child(n+2),
    .theos2-card:nth-child(n+2),
    .theos2-card span:nth-of-type(n+2),
    .sar-card span:nth-of-type(n+2),
    .dem-card span:nth-of-type(n+2) {
      display: none;
    }
    .local-library {
      display: grid;
      gap: 7px;
      margin: 6px 0 4px;
    }
    .local-counts {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 6px;
    }
    .local-chip {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px;
      background: #fbfcf8;
      min-width: 0;
    }
    .local-chip span {
      display: block;
      color: var(--muted);
      font-size: 11px;
      overflow-wrap: anywhere;
    }
    .local-chip strong {
      display: block;
      margin-top: 3px;
      font-size: 18px;
    }
    .readiness-card {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 10px;
      background: #fbfcf8;
      display: grid;
      gap: 3px;
      font-size: 12px;
    }
    .readiness-card strong {
      overflow-wrap: anywhere;
    }
    .readiness-card span {
      color: var(--muted);
      overflow-wrap: anywhere;
    }
    .manifest-links {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      font-size: 12px;
    }
    .manifest-links a {
      color: var(--green);
      text-decoration: none;
      border-bottom: 1px solid rgba(33, 131, 95, .35);
    }
    .delta-badge {
      display: inline-block;
      border-radius: 4px;
      padding: 2px 6px;
      background: #eef2ed;
      color: var(--ink);
      font-weight: 700;
    }
    .delta-badge.good { background: #dceee7; color: #14583f; }
    .delta-badge.bad { background: #f5dede; color: #812a2a; }
    .map-wrap {
      position: relative;
      min-width: 0;
    }
    .toolbar {
      position: static;
      z-index: auto;
      background: #fbfcf8;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 10px;
      display: flex;
      gap: 12px;
      font-size: 13px;
      box-shadow: none;
    }
    .toolbar label {
      display: flex;
      align-items: center;
      gap: 6px;
      white-space: nowrap;
    }
    #map {
      min-height: 0;
      height: 100%;
      width: 100%;
      position: relative;
    }
    .legend {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 8px;
      padding: 12px 16px;
      border-top: 1px solid var(--line);
      background: var(--panel);
      font-size: 12px;
    }
    .legend span {
      display: flex;
      align-items: center;
      gap: 6px;
      min-width: 0;
    }
    .swatch {
      width: 12px;
      height: 12px;
      border-radius: 3px;
      border: 1px solid rgba(32, 39, 34, .2);
      flex: 0 0 auto;
    }
    .docs {
      border-top: 1px solid var(--line);
      padding: 8px 16px 8px;
      background: var(--bg);
    }
    .doc-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 12px;
    }
    .doc-grid article {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      box-shadow: 0 8px 20px rgba(32, 39, 34, .04);
    }
    pre {
      margin: 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      background: #f6f7f1;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 9px;
      max-height: 76px;
      overflow: auto;
      font: 12px/1.45 Consolas, Monaco, monospace;
      color: #263027;
    }
    .report-heading {
      display: flex;
      align-items: baseline;
      gap: 6px;
      margin-bottom: 10px;
    }
    .report-heading h2 {
      margin: 0;
    }
    .report-heading span {
      color: var(--muted);
      font-size: 12px;
    }
    .validation-metric-grid {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 8px;
      margin-bottom: 8px;
    }
    .validation-metric {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 7px 8px;
      background: #fbfcf8;
      min-width: 0;
    }
    .validation-metric span {
      display: block;
      color: var(--muted);
      font-size: 11px;
      margin-bottom: 4px;
    }
    .validation-metric strong {
      font-size: 18px;
      line-height: 1.1;
    }
    .report-notes {
      margin: 0 0 8px;
      color: var(--muted);
      font-size: 12px;
    }
    .brief-summary {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 7px 9px;
      background: #fbfcf8;
      margin-bottom: 8px;
      font-size: 13px;
    }
    .brief-summary strong {
      display: block;
      margin-bottom: 5px;
    }
    .brief-summary ul {
      margin: 0;
      padding-left: 18px;
      color: var(--muted);
    }
    .app-footer {
      display: grid;
      grid-template-columns: minmax(220px, 1fr) minmax(260px, 1.3fr) minmax(180px, auto);
      gap: 12px;
      align-items: center;
      padding: 10px 16px 12px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 12px;
    }
    .app-footer strong {
      display: block;
      color: var(--ink);
      margin-bottom: 2px;
    }
    .note {
      font-size: 12px;
      color: var(--muted);
      margin-top: 12px;
    }
    @media (max-width: 1200px) {
      .kpi-strip { grid-template-columns: repeat(4, minmax(140px, 1fr)); }
      .dashboard-workspace {
        grid-template-columns: 280px minmax(520px, 1fr);
      }
      .decision-panel {
        grid-column: 1 / -1;
        max-height: none;
      }
    }
    @media (max-width: 900px) {
      .app-shell { padding: 10px; }
      .app-header { grid-template-columns: 1fr; }
      .status-row { justify-content: flex-start; }
      .kpi-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .dashboard-workspace {
        display: flex;
        flex-direction: column;
      }
      .control-panel,
      .map-panel,
      .decision-panel {
        margin-bottom: 12px;
        max-height: none;
      }
      .map-panel { order: 1; }
      .control-panel { order: 2; }
      .decision-panel { order: 3; }
      .map-panel {
        min-height: 560px;
        grid-template-rows: auto 500px;
      }
      .context-preview-grid {
        grid-template-columns: 1fr;
      }
      .map-legend {
        position: static;
        max-width: none;
        margin: 10px;
        grid-template-columns: 1fr;
      }
      .shell { display: block; }
      aside {
        border-right: 0;
        border-bottom: 1px solid var(--line);
      }
      .doc-grid { grid-template-columns: 1fr; }
      .legend { grid-template-columns: 1fr 1fr; }
      .app-footer { grid-template-columns: 1fr; }
      .validation-metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
  </style>
</head>
<body>
  <div class="app-shell">
    <header class="app-header" data-dashboard-section="app-header">
      <div class="brand-row">
        <div class="brand-mark" aria-hidden="true">FG</div>
        <div class="brand-copy">
          <h1>FloodGuard Decision Dashboard</h1>
          <p>Judge-demo command center for fixture-backed local prioritization. Not an official warning.</p>
        </div>
      </div>
      <div class="status-row" aria-label="Dashboard status">
        <span class="status-chip demo">Fixture demo</span>
        <span class="status-chip warn">Non-operational</span>
        <span class="status-chip blocked">Real validation blocked</span>
        <span class="timestamp">Static HTML | embedded data | no backend</span>
      </div>
    </header>

    <section class="kpi-strip" data-dashboard-section="kpi-strip" aria-label="Priority KPIs">
      <div class="kpi-card"><span class="label">Selected</span><span class="value" id="panel-subdistrict">__TOP_SUBDISTRICT__</span><span class="kpi-note">__TOP_NAME__</span></div>
      <div class="kpi-card"><span class="label">FPPS</span><span class="value" id="panel-fpps">__TOP_FPPS__</span><span class="kpi-note">0-100 priority score</span></div>
      <div class="kpi-card"><span class="label">Action class</span><span class="value" id="panel-class">__TOP_CLASS__</span><span class="kpi-note" id="panel-action-label">__TOP_ACTION_LABEL__</span></div>
      <div class="kpi-card"><span class="label">Confidence</span><span class="value" id="panel-confidence">__TOP_CONFIDENCE__</span><span class="kpi-note">fixture class</span></div>
      <div class="kpi-card"><span class="label">30-min access loss</span><span class="value" id="panel-baseline-access">__TOP_BASELINE_ACCESS__</span><span class="kpi-note">baseline people</span></div>
      <div class="kpi-card"><span class="label">Equity gap</span><span class="value" id="panel-baseline-equity">__TOP_BASELINE_EQUITY__</span><span class="kpi-note">ratio</span></div>
      <div class="kpi-card"><span class="label">Shelter scenario</span><span class="value"><span class="delta-badge" id="panel-temp-delta">__TOP_TEMP_DELTA__</span></span><span class="kpi-note">30-min access change</span></div>
      <div class="kpi-card"><span class="label">Road closure</span><span class="value"><span class="delta-badge" id="panel-road-delta">__TOP_ROAD_DELTA__</span></span><span class="kpi-note">stress-case change</span></div>
    </section>

    <section class="dashboard-workspace" data-dashboard-section="dashboard-workspace" aria-label="FloodGuard judge-demo workspace">
      <aside class="control-panel" data-dashboard-section="control-panel">
        <div class="panel-title">
          <h2>Controls &amp; Scenario</h2>
          <span>Scenario setup</span>
        </div>
        <div class="control-stack">
          <div>
            <label class="control-label" for="subdistrict-select">Subdistrict</label>
            <select id="subdistrict-select"></select>
          </div>
          <div>
            <span class="control-label">Action class filters</span>
            <div class="filter-row" id="action-class-filters" aria-label="Action class filters">
              <label><input class="action-filter" type="checkbox" value="A" checked> A</label>
              <label><input class="action-filter" type="checkbox" value="B" checked> B</label>
              <label><input class="action-filter" type="checkbox" value="C" checked> C</label>
              <label><input class="action-filter" type="checkbox" value="D" checked> D</label>
              <label><input class="action-filter" type="checkbox" value="E" checked> E</label>
            </div>
          </div>
          <div>
            <label class="control-label" for="scenario-select">Scenario mode</label>
            <select id="scenario-select">
              <option value="baseline">baseline</option>
              <option value="temporary_shelter">temporary shelter delta</option>
              <option value="road_closure">road closure delta</option>
            </select>
          </div>
          <div>
            <label class="control-label" for="dataset-mode-select">Dataset mode</label>
            <select id="dataset-mode-select">
              <option value="fixture_demo">Fixture demo</option>
              <option value="mae_sai_weak_reference">Mae Sai weak-reference candidate</option>
              <option value="metadata_blocker_view">Metadata/blocker view</option>
            </select>
          </div>
        </div>
        <div class="button-row" aria-label="Dashboard exports">
          <button id="download-current-brief" type="button">Download current brief</button>
          <button id="download-filtered-geojson" type="button">Download filtered GeoJSON</button>
        </div>
        <h2>Scenario Summary</h2>
        <div class="summary-card-grid">
          <div class="summary-card" id="summary-best-intervention">
            <span class="label">Best intervention effect</span>
            <strong>__BEST_INTERVENTION_LABEL__</strong>
            <span>Temporary shelter: __BEST_INTERVENTION_DELTA__ people losing 30-min access</span>
          </div>
          <div class="summary-card" id="summary-worst-road-closure">
            <span class="label">Worst road-closure stress case</span>
            <strong>__WORST_ROAD_CLOSURE_LABEL__</strong>
            <span>Road closure: __WORST_ROAD_CLOSURE_DELTA__ people losing 30-min access</span>
          </div>
        </div>
        <h2>Read This First</h2>
        <p class="dataset-mode-note" id="dataset-mode-note">Fixture demo: synthetic priority, access, equity, and road-risk outputs. Use this mode to judge the decision-layer workflow, not real flood accuracy.</p>
        <p><strong>Current status:</strong> Fixture-backed decision demo. It shows prioritization behavior but does not prove real flood-detection accuracy.</p>
        <ul class="compact-list">
          <li>Real Mae Sai validation is blocked until provider response pending items are resolved.</li>
          <li>Context layers are not flood labels, not reference masks, and not agency flood products.</li>
          <li>Real-data ML is not allowed until legal reference-mask and file-level gates pass.</li>
        </ul>
        __MAE_SAI_WEAK_CARD_HTML__
      </aside>

      <section class="map-panel" data-dashboard-section="map-panel" aria-label="FloodGuard map panel">
        <div class="map-heading">
          <div>
            <h2>Priority Map</h2>
            <p>Priority polygons and road-risk segments from embedded fixture GeoJSON.</p>
          </div>
          <div class="toolbar" aria-label="Layer toggles">
            <label><input id="toggle-priority" type="checkbox" checked> Priority</label>
            <label><input id="toggle-roads" type="checkbox" checked> Road risk</label>
          </div>
        </div>
        <div class="map-body">
          <div id="map"></div>
          <div class="map-legend" aria-label="Map legend">
            <div class="legend-group">
              <strong>Action class</strong>
              <span class="legend-item"><i class="swatch" style="background:#b73c3c"></i>A Protect Lives</span>
              <span class="legend-item"><i class="swatch" style="background:#d36a35"></i>B Routes</span>
              <span class="legend-item"><i class="swatch" style="background:#d8a629"></i>C Services</span>
              <span class="legend-item"><i class="swatch" style="background:#21835f"></i>D Resilience</span>
              <span class="legend-item"><i class="swatch" style="background:#6d5aa8"></i>E Monitor</span>
            </div>
            <div class="legend-group">
              <strong>Scenario and road risk</strong>
              <span class="legend-item"><i class="swatch" style="background:#21835f"></i>Delta improves</span>
              <span class="legend-item"><i class="swatch" style="background:#b73c3c"></i>Delta worsens</span>
              <span class="legend-item"><i class="swatch" style="background:#7f8a82"></i>Neutral/unavailable</span>
              <span class="legend-item"><i class="road-sample"></i>High road risk</span>
              <span class="legend-item"><i class="road-sample medium"></i>Medium road risk</span>
            </div>
          </div>
        </div>
      </section>

      <aside class="decision-panel" data-dashboard-section="decision-panel">
        <div class="panel-tabs" aria-label="Decision panel sections">
          <button class="panel-tab active" type="button">Action Brief</button>
          <button class="panel-tab" type="button">Context Assets</button>
          <button class="panel-tab" type="button">Data Readiness</button>
        </div>
        <section class="panel-section" id="decision-brief-panel">
          <div class="brief-heading-row">
            <strong id="panel-detail-title">__TOP_SUBDISTRICT__ / __TOP_NAME__</strong>
            <span class="class-pill" id="panel-detail-class">Class __TOP_CLASS__</span>
          </div>
          <p id="panel-reason">__TOP_REASON__</p>
          <ul class="summary-list">
            <li>Baseline 30-minute access loss: <strong id="panel-detail-access">__TOP_BASELINE_ACCESS__</strong></li>
            <li>Equity gap ratio: <strong id="panel-detail-equity">__TOP_BASELINE_EQUITY__</strong></li>
            <li>Temporary shelter delta: <strong id="panel-detail-temp">__TOP_TEMP_DELTA__</strong></li>
            <li>Road closure delta: <strong id="panel-detail-road">__TOP_ROAD_DELTA__</strong></li>
          </ul>
          <div class="safety-note">Context only. Not flood detection. Not validation. Not an official warning.</div>
        </section>
        <section class="panel-section" data-dashboard-section="context-readiness-panel">
          <div class="context-preview-heading">
            <h2>Context Assets</h2>
            <span>preview only; not flood labels</span>
          </div>
          <div class="context-preview-grid">
            <div>
              <h3>Sentinel-1 SAR Context</h3>
              <div class="sar-context" id="sentinel1-sar-context">
                __SENTINEL1_CONTEXT_HTML__
              </div>
            </div>
            <div>
              <h3>DEM Terrain Context</h3>
              <div class="dem-context" id="dem-terrain-context">
                __DEM_CONTEXT_HTML__
              </div>
            </div>
            <div>
              <h3>THEOS-2 Optical Context</h3>
              <div class="theos2-context" id="theos2-context">
                __THEOS2_CONTEXT_HTML__
              </div>
            </div>
          </div>
        </section>
        <section class="panel-section">
          <div class="panel-title">
            <h2>Local Data Library</h2>
            <span>processing gated</span>
          </div>
          <div class="local-library" id="local-data-library">
            __LOCAL_DATA_LIBRARY_HTML__
          </div>
        </section>
      </aside>
    </section>
  </div>

  <section class="docs report-section" data-dashboard-section="report-section">
    <div class="doc-grid">
      <article id="validation-summary">
        <div class="report-heading"><h2>Validation Summary</h2><span>Fixture Metrics</span></div>
        <div class="validation-metric-grid">__VALIDATION_METRIC_CARDS__</div>
        <p class="report-notes">Toy metrics are synthetic fixtures only. Real flood validation remains blocked until legal reference masks and file-level gates pass.</p>
        <pre>__VALIDATION_SUMMARY__</pre>
      </article>
      <article id="action-brief">
        <div class="report-heading"><h2>Action Brief</h2><span>Detailed</span></div>
        <div class="brief-summary">
          <strong>__TOP_SUBDISTRICT__ / __TOP_NAME__ (Class __TOP_CLASS__)</strong>
          <ul>
            <li>Immediate local action focus: __TOP_REASON__</li>
            <li>Access-loss impact: __TOP_BASELINE_ACCESS__ people losing 30-minute access.</li>
            <li>This is not an official warning. Use with local assessment and official advisories.</li>
          </ul>
        </div>
        <pre id="action-brief-pre">__INITIAL_BRIEF__</pre>
      </article>
    </div>
  </section>

  <footer class="app-footer" data-dashboard-section="app-footer">
    <div><strong>FloodGuard Thailand</strong>Preparedness and rapid post-event prioritization</div>
    <div>Data sources and assumptions are shown in this dashboard. See accompanying reports for details.</div>
    <div>Generated: 2025-07-07 08:00 ICT</div>
  </footer>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const priorityData = __PRIORITY_JSON__;
    const roadRiskData = __ROAD_JSON__;
    const briefsBySubdistrict = __BRIEFS_JSON__;
    const theos2PreviewData = __THEOS2_JSON__;
    const sentinel1QuicklookData = __SENTINEL1_QUICKLOOK_JSON__;
    const demQuicklookData = __DEM_QUICKLOOK_JSON__;
    const localDataLibrarySummary = __LOCAL_DATA_JSON__;
    const maeSaiWeakReferencePriorityData = __MAE_SAI_WEAK_JSON__;
    const actionColors = {
      A: '#b73c3c',
      B: '#d36a35',
      C: '#d8a629',
      D: '#21835f',
      E: '#6d5aa8'
    };
    const actionLabels = {
      A: 'Protect Lives Now',
      B: 'Keep Routes Open',
      C: 'Protect Essential Services',
      D: 'Build Resilience',
      E: 'Monitor and Verify'
    };
    const deltaColors = {
      improvement: '#21835f',
      worsening: '#b73c3c',
      neutral: '#7f8a82'
    };
    const datasetModeNotes = {
      fixture_demo: 'Fixture demo: synthetic priority, access, equity, and road-risk outputs. Use this mode to judge the decision-layer workflow, not real flood accuracy.',
      mae_sai_weak_reference: '__MAE_SAI_WEAK_NOTE__',
      metadata_blocker_view: 'Metadata/blocker view: source candidates and local files are documented, but official validation and real-data ML remain blocked until legal/reference-mask and file-level gates clear.'
    };
    const mapBoundsPadding = 0.16;
    const state = {
      selectedId: '__TOP_ID__',
      scenario: 'baseline',
      datasetMode: 'fixture_demo',
      visibleClasses: new Set(['A', 'B', 'C', 'D', 'E']),
      showPriority: true,
      showRoads: true
    };
    const featuresById = new Map(priorityData.features.map((feature) => [String(feature.properties.subdistrict_id), feature]));
    const featureLayers = new Map();

    const map = L.map('map', { scrollWheelZoom: false });
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);

    const priorityLayer = L.geoJSON(null, {
      style: priorityStyle,
      onEachFeature: bindPriorityFeature
    }).addTo(map);
    const roadLayer = L.geoJSON(roadRiskData, {
      style: roadStyle,
      onEachFeature: (feature, layer) => layer.bindPopup(popup(feature.properties))
    }).addTo(map);

    function initializeDashboardControls() {
      const selector = document.getElementById('subdistrict-select');
      priorityData.features
        .slice()
        .sort((left, right) => String(left.properties.subdistrict_id).localeCompare(String(right.properties.subdistrict_id)))
        .forEach((feature) => {
          const props = feature.properties;
          const option = document.createElement('option');
          option.value = props.subdistrict_id;
          option.textContent = `${props.subdistrict_id} / ${props.subdistrict_name}`;
          selector.appendChild(option);
        });
      selector.value = state.selectedId;
      selector.addEventListener('change', (event) => {
        selectSubdistrict(event.target.value, true);
      });

      document.querySelectorAll('.action-filter').forEach((input) => {
        input.addEventListener('change', () => {
          state.visibleClasses = new Set(
            [...document.querySelectorAll('.action-filter:checked')].map((item) => item.value)
          );
          renderPriorityLayer();
        });
      });

      document.getElementById('scenario-select').addEventListener('change', (event) => {
        state.scenario = event.target.value;
        renderPriorityLayer();
        updateSelectedPanel();
      });
      document.getElementById('dataset-mode-select').addEventListener('change', (event) => {
        state.datasetMode = event.target.value;
        updateSelectedPanel();
      });
      document.getElementById('toggle-priority').addEventListener('change', (event) => {
        state.showPriority = event.target.checked;
        state.showPriority ? priorityLayer.addTo(map) : priorityLayer.removeFrom(map);
      });
      document.getElementById('toggle-roads').addEventListener('change', (event) => {
        state.showRoads = event.target.checked;
        state.showRoads ? roadLayer.addTo(map) : roadLayer.removeFrom(map);
      });
      document.getElementById('download-current-brief').addEventListener('click', downloadCurrentActionBrief);
      document.getElementById('download-filtered-geojson').addEventListener('click', downloadFilteredGeoJSON);
    }

    function bindPriorityFeature(feature, layer) {
      const id = String(feature.properties.subdistrict_id);
      const name = String(feature.properties.subdistrict_name || '');
      featureLayers.set(id, layer);
      layer.bindPopup(popup(feature.properties));
      layer.bindTooltip(
        `<strong>${escapeHtml(id)}</strong><span>${escapeHtml(name)}</span>`,
        {
          permanent: true,
          direction: 'center',
          className: 'subdistrict-label'
        }
      );
      layer.on('click', () => selectSubdistrict(id, false));
    }

    function renderPriorityLayer() {
      featureLayers.clear();
      priorityLayer.clearLayers();
      const visibleFeatures = priorityData.features.filter((feature) =>
        state.visibleClasses.has(String(feature.properties.action_class))
      );
      if (state.showPriority) {
        priorityLayer.addData(visibleFeatures);
      }
    }

    function fitPriorityMapToData() {
      map.invalidateSize({ pan: false });
      const bounds = priorityLayer.getBounds();
      if (bounds.isValid()) {
        map.fitBounds(bounds.pad(mapBoundsPadding), { animate: false });
      } else {
        map.setView([18.02, 100.02], 13);
      }
    }

    function settleMapLayout() {
      fitPriorityMapToData();
      window.setTimeout(fitPriorityMapToData, 80);
      window.setTimeout(fitPriorityMapToData, 350);
    }

    function selectSubdistrict(subdistrictId, zoomToFeature) {
      state.selectedId = String(subdistrictId);
      document.getElementById('subdistrict-select').value = state.selectedId;
      updateSelectedPanel();
      renderPriorityLayer();
      if (zoomToFeature) {
        zoomToSelectedFeature();
      }
    }

    function updateSelectedPanel() {
      const feature = featuresById.get(state.selectedId);
      if (!feature) {
        return;
      }
      const props = feature.properties;
      setText('panel-subdistrict', `${props.subdistrict_id}`);
      setText('panel-class', props.action_class || 'unavailable');
      setText('panel-action-label', actionLabels[props.action_class] || 'unavailable');
      setText('panel-fpps', formatNumber(props.fpps_0_100, 2));
      setText('panel-confidence', props.confidence_class || 'unavailable');
      setText('panel-baseline-access', formatNumber(props.baseline_people_losing_30_min_access, 0));
      setText('panel-baseline-equity', formatNumber(props.baseline_equity_gap_ratio, 3));
      setDeltaBadge('panel-temp-delta', props.temporary_shelter_change_people_losing_30_min_access);
      setDeltaBadge('panel-road-delta', props.road_closure_change_people_losing_30_min_access);
      setText('panel-detail-title', `${props.subdistrict_id} / ${props.subdistrict_name || 'unavailable'}`);
      setText('panel-detail-class', `Class ${props.action_class || 'unavailable'}`);
      setText('panel-detail-access', formatNumber(props.baseline_people_losing_30_min_access, 0));
      setText('panel-detail-equity', formatNumber(props.baseline_equity_gap_ratio, 3));
      setText('panel-detail-temp', formatSigned(props.temporary_shelter_change_people_losing_30_min_access, 0));
      setText('panel-detail-road', formatSigned(props.road_closure_change_people_losing_30_min_access, 0));
      setText('panel-reason', props.top_reason || '');
      setText('dataset-mode-note', datasetModeNotes[state.datasetMode] || datasetModeNotes.fixture_demo);
      setText(
        'action-brief-pre',
        briefsBySubdistrict[state.selectedId] || 'No generated action brief for this subdistrict.'
      );
    }

    function zoomToSelectedFeature() {
      const layer = featureLayers.get(state.selectedId);
      if (!layer) {
        return;
      }
      if (typeof layer.getBounds === 'function') {
        map.fitBounds(layer.getBounds().pad(0.25));
      }
      layer.openPopup();
    }

    function priorityStyle(feature) {
      const props = feature.properties;
      const isSelected = String(props.subdistrict_id) === state.selectedId;
      const scenarioColor = scenarioFillColor(props);
      return {
        color: isSelected ? '#111814' : '#202722',
        weight: isSelected ? 3 : 1,
        fillColor: scenarioColor,
        fillOpacity: state.scenario === 'baseline' ? 0.45 : 0.6
      };
    }

    function scenarioFillColor(props) {
      if (state.scenario === 'baseline') {
        return actionColors[props.action_class] || actionColors.E;
      }
      const value = scenarioDelta(props);
      if (value === null || value === 0) {
        return deltaColors.neutral;
      }
      return value < 0 ? deltaColors.improvement : deltaColors.worsening;
    }

    function scenarioDelta(props) {
      const field = state.scenario === 'temporary_shelter'
        ? 'temporary_shelter_change_people_losing_30_min_access'
        : 'road_closure_change_people_losing_30_min_access';
      const value = Number(props[field]);
      return Number.isFinite(value) ? value : null;
    }

    function roadStyle(feature) {
      const risk = Number(feature.properties.road_disruption_probability_0_1 || 0);
      return {
        color: risk >= 0.7 ? '#b73c3c' : risk >= 0.5 ? '#d36a35' : '#21835f',
        weight: 3 + risk * 4,
        opacity: 0.9
      };
    }

    function popup(properties) {
      return Object.entries(properties)
        .map(([key, value]) => `<strong>${escapeHtml(key)}</strong>: ${escapeHtml(value ?? 'unavailable')}`)
        .join('<br>');
    }

    function escapeHtml(value) {
      return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }

    function formatNumber(value, places) {
      const number = Number(value);
      return Number.isFinite(number) ? number.toFixed(places) : 'unavailable';
    }

    function formatSigned(value, places) {
      const number = Number(value);
      if (!Number.isFinite(number)) {
        return 'unavailable';
      }
      return `${number > 0 ? '+' : ''}${number.toFixed(places)}`;
    }

    function setText(elementId, value) {
      const element = document.getElementById(elementId);
      if (element) {
        element.textContent = value;
      }
    }

    function setDeltaBadge(elementId, value) {
      const element = document.getElementById(elementId);
      if (!element) {
        return;
      }
      const number = Number(value);
      element.textContent = formatSigned(value, 0);
      element.classList.remove('good', 'bad');
      if (!Number.isFinite(number) || number === 0) {
        return;
      }
      element.classList.add(number < 0 ? 'good' : 'bad');
    }

    function downloadCurrentActionBrief() {
      const id = state.selectedId || 'selected';
      const content = briefsBySubdistrict[id] || `# FloodGuard Action Brief\n\nNo generated action brief for ${id}.\n`;
      downloadText(`action_brief_${sanitizeFilename(id)}.md`, content, 'text/markdown;charset=utf-8');
    }

    function downloadFilteredGeoJSON() {
      const filtered = {
        type: 'FeatureCollection',
        features: priorityData.features.filter((feature) =>
          state.visibleClasses.has(String(feature.properties.action_class))
        )
      };
      downloadText(
        'priority_subdistricts_filtered.geojson',
        JSON.stringify(filtered, null, 2),
        'application/geo+json;charset=utf-8'
      );
    }

    function downloadText(filename, content, mimeType) {
      const blob = new Blob([content], { type: mimeType });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    }

    function sanitizeFilename(value) {
      return String(value || 'selected').replace(/[^A-Za-z0-9_.-]/g, '_');
    }

    initializeDashboardControls();
    renderPriorityLayer();
    updateSelectedPanel();
    requestAnimationFrame(settleMapLayout);
    window.addEventListener('load', settleMapLayout);
    window.addEventListener('resize', settleMapLayout);
    if ('ResizeObserver' in window) {
      const mapPanel = document.querySelector('.map-panel');
      if (mapPanel) {
        new ResizeObserver(settleMapLayout).observe(mapPanel);
      }
    }
  </script>
</body>
</html>
"""

    top_id = str(props.get("subdistrict_id", ""))
    top_name = str(props.get("subdistrict_name", ""))
    top_class = str(props.get("action_class", ""))
    initial_brief = action_briefs.get(top_id) or next(iter(action_briefs.values()))
    replacements = {
        "__PRIORITY_JSON__": json.dumps(priority_geojson, ensure_ascii=False),
        "__ROAD_JSON__": json.dumps(road_risk_geojson, ensure_ascii=False),
        "__BRIEFS_JSON__": json.dumps(action_briefs, ensure_ascii=False),
        "__THEOS2_JSON__": json.dumps(theos2_preview_rows, ensure_ascii=False),
        "__SENTINEL1_QUICKLOOK_JSON__": json.dumps(
            sentinel1_quicklook_rows,
            ensure_ascii=False,
        ),
        "__DEM_QUICKLOOK_JSON__": json.dumps(dem_quicklook_rows, ensure_ascii=False),
        "__LOCAL_DATA_JSON__": json.dumps(local_data_summary, ensure_ascii=False),
        "__MAE_SAI_WEAK_JSON__": json.dumps(
            mae_sai_weak_summary,
            ensure_ascii=False,
        ),
        "__MAE_SAI_WEAK_NOTE__": _js_string(
            _mae_sai_weak_dataset_note(mae_sai_weak_summary)
        ),
        "__MAE_SAI_WEAK_CARD_HTML__": _mae_sai_weak_card_html(
            mae_sai_weak_summary
        ),
        "__THEOS2_CONTEXT_HTML__": _theos2_context_html(theos2_preview_rows),
        "__SENTINEL1_CONTEXT_HTML__": _sentinel1_context_html(
            sentinel1_quicklook_rows
        ),
        "__DEM_CONTEXT_HTML__": _dem_context_html(dem_quicklook_rows),
        "__LOCAL_DATA_LIBRARY_HTML__": _local_data_library_html(local_data_summary),
        "__VALIDATION_METRIC_CARDS__": _validation_metric_cards_html(
            validation_metric_cards
        ),
        "__VALIDATION_SUMMARY__": html.escape(validation_summary),
        "__INITIAL_BRIEF__": html.escape(initial_brief),
        "__TOP_ID__": _js_string(top_id),
        "__TOP_SUBDISTRICT__": html.escape(top_id),
        "__TOP_NAME__": html.escape(top_name),
        "__TOP_CLASS__": html.escape(top_class),
        "__TOP_ACTION_LABEL__": html.escape(_action_label(top_class)),
        "__TOP_FPPS__": _format_number(props.get("fpps_0_100"), 2),
        "__TOP_CONFIDENCE__": html.escape(str(props.get("confidence_class", ""))),
        "__TOP_BASELINE_ACCESS__": _format_number(
            props.get("baseline_people_losing_30_min_access"),
            0,
        ),
        "__TOP_BASELINE_EQUITY__": _format_number(
            props.get("baseline_equity_gap_ratio"),
            3,
        ),
        "__TOP_TEMP_DELTA__": _format_signed(
            props.get("temporary_shelter_change_people_losing_30_min_access"),
            0,
        ),
        "__TOP_ROAD_DELTA__": _format_signed(
            props.get("road_closure_change_people_losing_30_min_access"),
            0,
        ),
        "__TOP_REASON__": html.escape(str(props.get("top_reason", ""))),
        "__BEST_INTERVENTION_LABEL__": html.escape(best_intervention["label"]),
        "__BEST_INTERVENTION_DELTA__": html.escape(best_intervention["delta"]),
        "__WORST_ROAD_CLOSURE_LABEL__": html.escape(worst_road_closure["label"]),
        "__WORST_ROAD_CLOSURE_DELTA__": html.escape(worst_road_closure["delta"]),
    }
    for token, value in replacements.items():
        template = template.replace(token, value)
    return template


def _format_number(value: object, places: int) -> str:
    try:
        numeric = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "unavailable"
    return f"{numeric:.{places}f}"


def _action_label(action_class: str) -> str:
    labels = {
        "A": "Protect Lives Now",
        "B": "Keep Routes Open",
        "C": "Protect Essential Services",
        "D": "Build Resilience",
        "E": "Monitor and Verify",
    }
    return labels.get(action_class, "unavailable")


def _format_signed(value: object, places: int) -> str:
    try:
        numeric = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "unavailable"
    sign = "+" if numeric > 0 else ""
    return f"{sign}{numeric:.{places}f}"


def _js_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)[1:-1]


def _scenario_summary(
    priority_geojson: dict[str, Any],
    delta_field: str,
    prefer: str,
) -> dict[str, str]:
    candidates: list[tuple[float, str, str]] = []
    for feature in priority_geojson.get("features", []):
        props = feature.get("properties") or {}
        try:
            delta = float(props[delta_field])
        except (KeyError, TypeError, ValueError):
            continue
        if delta != delta:
            continue
        label = f"{props.get('subdistrict_id', '')} / {props.get('subdistrict_name', '')}"
        candidates.append((delta, label, str(props.get("action_class", ""))))
    if not candidates:
        return {"label": "unavailable", "delta": "unavailable"}
    if prefer == "min":
        delta, label, _ = min(candidates, key=lambda item: (item[0], item[1]))
    elif prefer == "max":
        delta, label, _ = max(candidates, key=lambda item: (item[0], item[1]))
    else:
        raise DashboardError(f"Unknown scenario summary preference: {prefer}")
    return {"label": label, "delta": _format_signed(delta, 0)}


def _read_validation_metric_cards(output_dir: Path) -> list[dict[str, str]]:
    rows = _read_csv_rows(output_dir / "sample_sar_validation_metrics.csv")
    if not rows:
        return [
            {"label": "IoU", "value": "pending"},
            {"label": "F1 / Dice", "value": "pending"},
            {"label": "Precision", "value": "pending"},
            {"label": "Recall", "value": "pending"},
            {"label": "Area Error", "value": "pending"},
        ]

    row = rows[0]
    return [
        {"label": "IoU", "value": _format_metric_value(row.get("iou"))},
        {"label": "F1 / Dice", "value": _format_metric_value(row.get("f1_dice"))},
        {"label": "Precision", "value": _format_metric_value(row.get("precision"))},
        {"label": "Recall", "value": _format_metric_value(row.get("recall"))},
        {
            "label": "Area Error",
            "value": _format_metric_value(
                row.get("area_error_ratio"),
                signed=True,
                percent=True,
            ),
        },
    ]


def _read_mae_sai_weak_priority_summary(output_dir: Path) -> dict[str, Any]:
    path = output_dir / "mae_sai_priority_subdistricts.geojson"
    metrics_row = _first_csv_row(output_dir / "mae_sai_weak_baseline_metrics.csv")
    feature_row = _first_csv_row(output_dir / "mae_sai_weak_sar_feature_manifest.csv")
    reference_row = _first_csv_row(output_dir / "manual_reference_mask_manifest.csv")

    summary: dict[str, Any] = {
        "metrics_available": bool(metrics_row),
        "feature_manifest_available": bool(feature_row),
        "manual_reference_available": bool(reference_row),
        "pre_product_id": feature_row.get("pre_product_id", "unavailable")
        if feature_row
        else "unavailable",
        "post_product_id": feature_row.get("post_product_id", "unavailable")
        if feature_row
        else "unavailable",
        "reference_id": reference_row.get("reference_id", "unavailable")
        if reference_row
        else feature_row.get("reference_product_id", "unavailable")
        if feature_row
        else "unavailable",
        "manual_reference_status": reference_row.get(
            "reference_mask_status",
            "unavailable",
        )
        if reference_row
        else "unavailable",
        "candidate_readiness_status": reference_row.get(
            "candidate_readiness_status",
            "unavailable",
        )
        if reference_row
        else "unavailable",
        "not_official_status": reference_row.get(
            "not_official_status",
            "unavailable",
        )
        if reference_row
        else "unavailable",
        "iou": _format_number(metrics_row.get("iou"), 6)
        if metrics_row
        else "unavailable",
        "f1_dice": _format_number(metrics_row.get("f1_dice"), 6)
        if metrics_row
        else "unavailable",
        "precision": _format_number(metrics_row.get("precision"), 6)
        if metrics_row
        else "unavailable",
        "recall": _format_number(metrics_row.get("recall"), 6)
        if metrics_row
        else "unavailable",
        "area_error_ratio": _format_signed(metrics_row.get("area_error_ratio"), 6)
        if metrics_row
        else "unavailable",
        "warning_text": metrics_row.get(
            "warning_text",
            "Candidate metrics against manually digitized weak-reference mask. "
            "Non-operational. Not official validation. Not field validated.",
        )
        if metrics_row
        else (
            "Weak-reference candidate metrics have not been generated. "
            "Non-operational. Not official validation. Not field validated."
        ),
        "sample_pixel_count": metrics_row.get("sample_pixel_count", "unavailable")
        if metrics_row
        else "unavailable",
        "reference_positive_pixel_count": metrics_row.get(
            "reference_positive_pixel_count",
            "unavailable",
        )
        if metrics_row
        else "unavailable",
        "predicted_positive_pixel_count": metrics_row.get(
            "predicted_positive_pixel_count",
            "unavailable",
        )
        if metrics_row
        else "unavailable",
        "mean_flood_probability_0_1": _format_number(
            feature_row.get("mean_flood_probability_0_1"),
            6,
        )
        if feature_row
        else "unavailable",
    }

    if not path.exists():
        summary.update(
            {"available": False, "feature_count": 0, "status": "not_generated"}
        )
        return summary
    try:
        geojson = _read_feature_collection(path, "mae_sai_weak_priority")
    except DashboardError:
        summary.update(
            {"available": False, "feature_count": 0, "status": "invalid_geojson"}
        )
        return summary
    features = geojson.get("features", [])
    if not features:
        summary.update(
            {"available": False, "feature_count": 0, "status": "empty_geojson"}
        )
        return summary
    props = features[0].get("properties") or {}
    summary.update(
        {
            "available": True,
            "feature_count": len(features),
            "status": "weak_reference_decision_bridge_available",
            "subdistrict_id": str(props.get("subdistrict_id", "unavailable")),
            "subdistrict_name": str(props.get("subdistrict_name", "unavailable")),
            "fpps_0_100": _format_number(props.get("fpps_0_100"), 2),
            "action_class": str(props.get("action_class", "unavailable")),
            "mean_flood_probability_0_1": _format_number(
                props.get(
                    "mean_flood_probability_0_1",
                    summary.get("mean_flood_probability_0_1"),
                ),
                6,
            ),
            "confidence_class": str(props.get("confidence_class", "unavailable")),
            "reference_status": str(props.get("reference_status", "unavailable")),
            "context_status": str(props.get("context_status", "unavailable")),
            "source_timestamp": str(props.get("source_timestamp", "unavailable")),
        }
    )
    return summary


def _mae_sai_weak_dataset_note(summary: dict[str, Any]) -> str:
    base = (
        "Mae Sai weak-reference candidate: this mode is separated from the "
        "fixture demo. It summarizes downloaded outside-Git CDSE Sentinel-1 "
        "pre/post products, a manual QGIS weak-reference mask, candidate "
        "metrics, and the low-confidence decision bridge."
    )
    if not summary.get("available"):
        return (
            f"{base} The real-data decision output is not generated yet. This "
            "remains non-operational, not official validation, not field "
            "validated, and not an official warning."
        )
    return (
        f"{base} The weak-reference decision bridge is available with "
        f"{summary.get('feature_count')} review-area feature, FPPS "
        f"{summary.get('fpps_0_100')}, class {summary.get('action_class')}, "
        f"mean flood probability {summary.get('mean_flood_probability_0_1')}, "
        f"IoU {summary.get('iou')}, F1/Dice {summary.get('f1_dice')}, "
        f"precision {summary.get('precision')}, recall {summary.get('recall')}, "
        f"area error {summary.get('area_error_ratio')}, and confidence "
        f"{summary.get('confidence_class')}. This remains "
        "weak-reference, non-operational, not official validation, and not field "
        "validated. Not an official warning."
    )


def _mae_sai_weak_card_html(summary: dict[str, Any]) -> str:
    """Render a compact Mae Sai weak-reference card for the status narrative."""

    if not any(
        summary.get(key)
        for key in ("available", "metrics_available", "manual_reference_available")
    ):
        return (
            '<div class="mae-sai-weak-card" id="mae-sai-weak-reference-card">'
            "<strong>Mae Sai weak-reference candidate</strong>"
            "<p>Real-data candidate outputs have not been generated yet. This "
            "mode remains metadata-only, non-operational, and not an official "
            "warning.</p>"
            "</div>"
        )

    fields = [
        ("Pre S1 product", summary.get("pre_product_id", "unavailable")),
        ("Post S1 product", summary.get("post_product_id", "unavailable")),
        ("Manual mask", summary.get("reference_id", "unavailable")),
        ("Mask status", summary.get("manual_reference_status", "unavailable")),
        (
            "Candidate status",
            summary.get("candidate_readiness_status", "unavailable"),
        ),
        ("Not official", summary.get("not_official_status", "unavailable")),
        ("Mean flood probability", summary.get("mean_flood_probability_0_1")),
        (
            "Candidate metrics",
            (
                f"IoU {summary.get('iou')}; F1 {summary.get('f1_dice')}; "
                f"precision {summary.get('precision')}; "
                f"recall {summary.get('recall')}; "
                f"area error {summary.get('area_error_ratio')}"
            ),
        ),
        (
            "Decision output",
            (
                f"{summary.get('subdistrict_id', 'unavailable')}, FPPS "
                f"{summary.get('fpps_0_100', 'unavailable')}, class "
                f"{summary.get('action_class', 'unavailable')}, confidence "
                f"{summary.get('confidence_class', 'unavailable')}"
            ),
        ),
        ("Context status", summary.get("context_status", "unavailable")),
    ]
    definition_rows = "".join(
        f"<dt>{html.escape(label)}</dt><dd>{html.escape(str(value))}</dd>"
        for label, value in fields
    )
    warning = html.escape(
        f"{summary.get('warning_text')} Not an official warning."
    )
    return (
        '<div class="mae-sai-weak-card" id="mae-sai-weak-reference-card">'
        "<strong>Mae Sai weak-reference candidate</strong>"
        f"<dl>{definition_rows}</dl>"
        f'<div class="warning">{warning}</div>'
        "</div>"
    )


def _first_csv_row(path: Path) -> dict[str, str]:
    rows = _read_csv_rows(path)
    return rows[0] if rows else {}


def _format_metric_value(
    value: object,
    *,
    signed: bool = False,
    percent: bool = False,
) -> str:
    try:
        numeric = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "pending"
    if percent:
        numeric *= 100
        prefix = "+" if signed and numeric > 0 else ""
        return f"{prefix}{numeric:.1f}%"
    prefix = "+" if signed and numeric > 0 else ""
    return f"{prefix}{numeric:.2f}"


def _validation_metric_cards_html(cards: list[dict[str, str]]) -> str:
    return "".join(
        [
            '<div class="validation-metric">'
            f"<span>{html.escape(card['label'])}</span>"
            f"<strong>{html.escape(card['value'])}</strong>"
            "</div>"
            for card in cards
        ]
    )


def _local_data_library_html(summary: dict[str, Any]) -> str:
    counts = summary.get("library_counts", {})
    sentinel = summary.get("sentinel1", {})
    dem = summary.get("dem", {})
    theos2 = summary.get("theos2", {})
    links = summary.get("links", [])
    return "\n".join(
        [
            '<div class="local-counts" aria-label="Local data counts by group">',
            _local_count_chip("sentinel1_sar", counts.get("sentinel1_sar", 0)),
            _local_count_chip("copernicus_dem", counts.get("copernicus_dem", 0)),
            _local_count_chip("theos2_optical", counts.get("theos2_optical", 0)),
            "</div>",
            '<div class="readiness-card">',
            "<strong>Local Sentinel-1 readiness</strong>",
            f"<span>Asset: {html.escape(str(sentinel.get('file_name', 'unavailable')))}</span>",
            f"<span>Mae Sai overlap: {html.escape(str(sentinel.get('mvp_overlap', 'unavailable')))}</span>",
            f"<span>Bands: {html.escape(str(sentinel.get('band_descriptions', 'unavailable')))}</span>",
            f"<span>Checksum: {html.escape(str(sentinel.get('sha256_status', 'unavailable')))}</span>",
            f"<span>SAR quicklooks: {html.escape(str(sentinel.get('quicklook_count', 0)))}</span>",
            "</div>",
            '<div class="readiness-card">',
            "<strong>Sentinel-1 provenance status</strong>",
            f"<span>Candidate role: {html.escape(str(sentinel.get('candidate_role', 'unavailable')))}</span>",
            f"<span>Event timing: {html.escape(str(sentinel.get('event_timing_status', 'unavailable')))}</span>",
            f"<span>Provenance: {html.escape(str(sentinel.get('provenance_status', 'unavailable')))}</span>",
            f"<span>Blocked: {html.escape(str(sentinel.get('blocked_reason', 'unavailable')))}</span>",
            "</div>",
            '<div class="readiness-card">',
            "<strong>DEM readiness</strong>",
            f"<span>Packages: {html.escape(str(dem.get('package_count', 0)))}; DEM members: {html.escape(str(dem.get('member_count', 0)))}</span>",
            f"<span>DEM quicklooks: {html.escape(str(dem.get('quicklook_count', 0)))}</span>",
            f"<span>Status: terrain context only; {html.escape(str(dem.get('processing_scope', 'unavailable')))}</span>",
            f"<span>Checksum: {html.escape(str(dem.get('package_sha256_status', 'unavailable')))}</span>",
            f"<span>Not flood observation: {html.escape(str(dem.get('flood_observation_status', 'unavailable')))}</span>",
            f"<span>Not flood label: {html.escape(str(dem.get('flood_label_status', 'unavailable')))}</span>",
            "</div>",
            '<div class="readiness-card">',
            "<strong>THEOS-2 optical context readiness</strong>",
            f"<span>Selected files: {html.escape(str(theos2.get('selected_count', 0)))}; true thumbnails: {html.escape(str(theos2.get('thumbnail_count', 0)))}</span>",
            f"<span>Status: optical context only; {html.escape(str(theos2.get('processing_scope', 'unavailable')))}</span>",
            f"<span>Checksum: {html.escape(str(theos2.get('sha256_status', 'unavailable')))}</span>",
            f"<span>Reference mask status: {html.escape(str(theos2.get('reference_mask_status', 'unavailable')))}</span>",
            "</div>",
            f'<p class="note">{html.escape(str(summary.get("status_note", "")))}</p>',
            _manifest_links_html(links),
        ]
    )


def _local_count_chip(label: str, count: object) -> str:
    return (
        '<div class="local-chip">'
        f"<span>{html.escape(label)}</span>"
        f"<strong>{html.escape(str(count))}</strong>"
        "</div>"
    )


def _manifest_links_html(links: list[dict[str, str]]) -> str:
    if not links:
        return ""
    anchors = [
        f'<a href="{html.escape(link["href"])}">{html.escape(link["label"])}</a>'
        for link in links
        if link.get("href") and link.get("label")
    ]
    return '<div class="manifest-links">CSV summaries: ' + " ".join(anchors) + "</div>"


def _sentinel1_context_html(rows: list[dict[str, str]]) -> str:
    if not rows:
        return (
            '<p class="note">Sentinel-1 SAR quicklooks have not been generated. '
            "SAR context remains checksum-gated and event timing remains unresolved.</p>"
        )
    cards: list[str] = []
    for row in rows[:2]:
        file_name = html.escape(row.get("file_name", "unknown"))
        band = html.escape(row.get("band", "SAR"))
        quicklook_path = html.escape(row.get("quicklook_path", ""))
        sha_prefix = html.escape(row.get("sha256_prefix", ""))
        timing = html.escape(row.get("event_timing_status", "timing_unresolved"))
        provenance = html.escape(row.get("provenance_status", "unresolved"))
        warning = html.escape(
            row.get(
                "warning_text",
                "SAR context only; not flood detection; not validation; not an "
                "official warning; event timing unresolved unless proven otherwise.",
            )
        )
        cards.append(
            '<div class="sar-card">'
            f'<img src="{quicklook_path}" alt="Sentinel-1 SAR context quicklook {band}">'
            f"<strong>Sentinel-1 {band} SAR quicklook</strong>"
            f"<span>Source: {file_name}</span>"
            f"<span>Timing: {timing}</span>"
            f"<span>Provenance: {provenance}</span>"
            f"<span>SHA-256 prefix: {sha_prefix}</span>"
            f"<span>{warning}</span>"
            "</div>"
        )
    return "\n".join(cards)


def _dem_context_html(rows: list[dict[str, str]]) -> str:
    if not rows:
        return (
            '<p class="note">DEM terrain quicklook has not been generated. DEM remains '
            "terrain context only and requires extracted member checksums outside Git.</p>"
        )
    cards: list[str] = []
    for row in rows[:1]:
        member_name = html.escape(row.get("member_name", "unknown"))
        quicklook_path = html.escape(row.get("quicklook_path", ""))
        package_prefix = html.escape(row.get("package_sha256_prefix", ""))
        member_prefix = html.escape(row.get("member_sha256_prefix", ""))
        warning = html.escape(
            row.get(
                "warning_text",
                "DEM terrain context only; not flood observation; not flood label; "
                "not reference mask; not an official warning.",
            )
        )
        cards.append(
            '<div class="dem-card">'
            f'<img src="{quicklook_path}" alt="DEM terrain context quicklook">'
            "<strong>DEM terrain quicklook</strong>"
            f"<span>Member: {member_name}</span>"
            f"<span>Package SHA-256 prefix: {package_prefix}</span>"
            f"<span>Member SHA-256 prefix: {member_prefix}</span>"
            f"<span>{warning}</span>"
            "</div>"
        )
    return "\n".join(cards)


def _theos2_context_html(rows: list[dict[str, str]]) -> str:
    if not rows:
        return (
            '<p class="note">THEOS-2 preview manifest not generated yet. '
            "Optical context remains available in the metadata inventory.</p>"
        )
    cards: list[str] = []
    for row in rows[:3]:
        file_name = html.escape(row.get("file_name", "unknown"))
        category = html.escape(row.get("category", "unclassified"))
        timestamp = html.escape(row.get("source_timestamp", "unavailable"))
        preview_path = html.escape(row.get("preview_path", ""))
        sha_prefix = html.escape(row.get("sha256", "")[:12])
        thumbnail_format = row.get("thumbnail_format", "")
        raster_reader = row.get("raster_reader", "")
        if thumbnail_format:
            preview_kind = f"True {thumbnail_format.upper()} thumbnail"
            if raster_reader:
                preview_kind = f"{preview_kind} via {raster_reader}"
        else:
            preview_kind = "Metadata SVG preview card"
        preview_kind = html.escape(preview_kind)
        cards.append(
            '<div class="theos2-card">'
            f'<img src="{preview_path}" alt="THEOS-2 optical context preview for {file_name}">'
            f"<strong>{file_name}</strong>"
            f"<span>Category: {category}</span>"
            f"<span>Acquisition: {timestamp}</span>"
            f"<span>Preview: {preview_kind}</span>"
            f"<span>SHA-256 prefix: {sha_prefix}</span>"
            "<span>Optical context only; not flood validation or an official warning.</span>"
            "</div>"
        )
    return "\n".join(cards)


def _resolve_manifest_path(
    output_dir: Path,
    explicit_path: str | Path | None,
    default_name: str,
) -> Path | None:
    if explicit_path is not None:
        path = Path(explicit_path)
        return path if path.exists() else None
    path = output_dir / default_name
    return path if path.exists() else None


def _read_csv_rows(path: Path | None) -> list[dict[str, str]]:
    if path is None or not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _counts_by_field(rows: list[dict[str, str]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(field, "")
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return counts


def _first_row(rows: list[dict[str, str]]) -> dict[str, str]:
    return rows[0] if rows else {}


def _first_nonblank(rows: list[dict[str, str]], field: str) -> str:
    for row in rows:
        value = row.get(field, "")
        if value:
            return value
    return "unavailable"


def _common_status(rows: list[dict[str, str]], field: str) -> str:
    values = sorted({row.get(field, "") for row in rows if row.get(field, "")})
    if not values:
        return "unavailable"
    if len(values) == 1:
        return values[0]
    return "|".join(values)
