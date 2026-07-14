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
    mae_sai_priority_geojson_path: str | Path | None = None,
    mae_sai_road_risk_geojson_path: str | Path | None = None,
    mae_sai_facilities_geojson_path: str | Path | None = None,
    mae_sai_access_hotspots_geojson_path: str | Path | None = None,
    mae_sai_context_quality_path: str | Path | None = None,
    mae_sai_sar_context_path: str | Path | None = None,
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
    mae_sai_validation_path = output_dir / "mae_sai_validation_summary.md"
    mae_sai_validation_summary = (
        mae_sai_validation_path.read_text(encoding="utf-8")
        if mae_sai_validation_path.exists()
        else "Mae Sai weak-reference validation summary is unavailable."
    )
    mae_sai_priority_geojson = _read_optional_feature_collection(
        output_dir,
        mae_sai_priority_geojson_path,
        "mae_sai_priority_subdistricts.geojson",
        "mae_sai_priority",
    )
    mae_sai_road_risk_geojson = _read_optional_feature_collection(
        output_dir,
        mae_sai_road_risk_geojson_path,
        "mae_sai_road_risk.geojson",
        "mae_sai_road_risk",
    )
    mae_sai_facilities_geojson = _read_optional_feature_collection(
        output_dir,
        mae_sai_facilities_geojson_path,
        "mae_sai_facilities.geojson",
        "mae_sai_facilities",
    )
    mae_sai_access_hotspots_geojson = _read_optional_feature_collection(
        output_dir,
        mae_sai_access_hotspots_geojson_path,
        "mae_sai_access_hotspots.geojson",
        "mae_sai_access_hotspots",
    )
    mae_sai_context_quality = _first_csv_row(
        Path(mae_sai_context_quality_path)
        if mae_sai_context_quality_path is not None
        else output_dir / "mae_sai_context_quality_summary.csv"
    )
    mae_sai_sar_context = _csv_rows_by_key(
        Path(mae_sai_sar_context_path)
        if mae_sai_sar_context_path is not None
        else output_dir / "mae_sai_adm3_sar_context.csv",
        "subdistrict_id",
    )
    mae_sai_action_briefs = _read_mae_sai_action_briefs(output_dir)

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
        mae_sai_priority_geojson=mae_sai_priority_geojson,
        mae_sai_road_risk_geojson=mae_sai_road_risk_geojson,
        mae_sai_facilities_geojson=mae_sai_facilities_geojson,
        mae_sai_access_hotspots_geojson=mae_sai_access_hotspots_geojson,
        mae_sai_context_quality=mae_sai_context_quality,
        mae_sai_sar_context=mae_sai_sar_context,
        mae_sai_action_briefs=mae_sai_action_briefs,
        mae_sai_validation_summary=mae_sai_validation_summary,
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


def _read_optional_feature_collection(
    output_dir: Path,
    explicit_path: str | Path | None,
    default_name: str,
    label: str,
) -> dict[str, Any]:
    path = Path(explicit_path) if explicit_path is not None else output_dir / default_name
    if not path.exists():
        return {"type": "FeatureCollection", "features": []}
    return _read_feature_collection(path, label)


def _read_mae_sai_action_briefs(output_dir: Path) -> dict[str, str]:
    prefix = "mae_sai_action_brief_"
    briefs: dict[str, str] = {}
    for path in sorted(output_dir.glob(f"{prefix}*.md")):
        subdistrict_id = path.stem.removeprefix(prefix)
        if subdistrict_id:
            briefs[subdistrict_id] = path.read_text(encoding="utf-8")
    return briefs


def _csv_rows_by_key(path: Path, key: str) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return {str(row.get(key, "")): row for row in rows if row.get(key)}


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
    mae_sai_priority_geojson: dict[str, Any],
    mae_sai_road_risk_geojson: dict[str, Any],
    mae_sai_facilities_geojson: dict[str, Any],
    mae_sai_access_hotspots_geojson: dict[str, Any],
    mae_sai_context_quality: dict[str, str],
    mae_sai_sar_context: dict[str, dict[str, str]],
    mae_sai_action_briefs: dict[str, str],
    mae_sai_validation_summary: str,
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
      --font-sans: "Segoe UI", Inter, Arial, sans-serif;
      --font-thai: "Noto Sans Thai", "Leelawadee UI", Tahoma, sans-serif;
      --bg: #f3f6f4;
      --panel: #ffffff;
      --panel-subtle: #f8faf9;
      --ink: #15241f;
      --muted: #607169;
      --line: #d9e3de;
      --line-strong: #bdcbc4;
      --brand: #0f6b62;
      --brand-soft: #e8f4f1;
      --green: #167a55;
      --red: #c13f3f;
      --orange: #cf6a32;
      --yellow: #d39d20;
      --violet: #6956a3;
      --blue: #2867b8;
      --neutral: #7b8982;
      --warning-bg: #fff8e8;
      --warning-line: #e5c36e;
      --radius-sm: 5px;
      --radius-md: 7px;
      --radius-lg: 8px;
      --shadow-sm: 0 4px 14px rgba(26, 48, 39, .05);
      --shadow-md: 0 12px 30px rgba(26, 48, 39, .09);
      --space-1: 4px;
      --space-2: 8px;
      --space-3: 12px;
      --space-4: 16px;
      --space-5: 20px;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: var(--font-sans);
      line-height: 1.45;
      font-size: 14px;
    }
    html[lang="th"] body { font-family: var(--font-thai); }
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
      gap: var(--space-3);
      padding: 14px 18px 0;
      max-width: 2200px;
      margin: 0 auto;
    }
    .app-header {
      display: grid;
      grid-template-columns: minmax(320px, 1fr) auto;
      align-items: center;
      gap: 16px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius-lg);
      padding: 12px 16px;
      box-shadow: var(--shadow-sm);
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
      font-size: 23px;
      white-space: nowrap;
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
    .header-side {
      display: grid;
      justify-items: end;
      gap: 8px;
    }
    .display-controls {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 8px;
      flex-wrap: wrap;
    }
    .segmented-control {
      display: inline-grid;
      grid-template-columns: repeat(2, 36px);
      padding: 2px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: var(--panel-subtle);
    }
    .segment-button {
      min-height: 28px;
      padding: 4px 7px;
      border: 0;
      border-radius: 5px;
      background: transparent;
      color: var(--muted);
      font-size: 11px;
      font-weight: 800;
    }
    .segment-button[aria-pressed="true"] {
      background: var(--panel);
      color: var(--brand);
      box-shadow: 0 1px 4px rgba(26, 48, 39, .12);
    }
    .judge-toggle {
      min-height: 32px;
      padding: 5px 9px;
      border-color: var(--line-strong);
      background: var(--panel);
      color: var(--brand);
      font-size: 11px;
      font-weight: 800;
    }
    .judge-toggle[aria-pressed="true"] {
      border-color: var(--brand);
      background: var(--brand);
      color: #fff;
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
      gap: var(--space-2);
    }
    .kpi-card {
      min-width: 0;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius-md);
      padding: 11px 12px;
      display: grid;
      gap: 4px;
      box-shadow: var(--shadow-sm);
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
      height: clamp(540px, calc(100vh - 330px), 620px);
      min-height: 540px;
      display: grid;
      grid-template-columns: minmax(238px, 270px) minmax(520px, 1fr) minmax(350px, 410px);
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
      font-size: 9px;
      font-weight: 700;
      line-height: 1.08;
      text-align: center;
      text-shadow: 0 1px 2px rgba(255, 255, 255, .9);
      white-space: normal;
      width: 64px;
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
    .mode-warning {
      position: sticky;
      top: 6px;
      z-index: 900;
      display: grid;
      grid-template-columns: auto minmax(0, 1fr) auto;
      align-items: center;
      gap: 10px;
      min-height: 42px;
      padding: 8px 12px;
      border: 1px solid #a9c7bd;
      border-radius: var(--radius-md);
      background: #edf7f4;
      box-shadow: var(--shadow-sm);
      color: #174b40;
      font-size: 12px;
    }
    .mode-warning.weak-reference {
      border-color: var(--warning-line);
      background: var(--warning-bg);
      color: #78500a;
    }
    .mode-warning.blocked {
      border-color: #e6b2b2;
      background: #fff3f3;
      color: #8c2f2f;
    }
    .mode-warning strong { white-space: nowrap; }
    .mode-warning span { overflow-wrap: anywhere; }
    .mode-warning .warning-status {
      border: 1px solid currentColor;
      border-radius: 999px;
      padding: 3px 7px;
      font-weight: 700;
      white-space: nowrap;
    }
    .dataset-badge {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      border: 1px solid var(--line-strong);
      border-radius: 999px;
      padding: 3px 8px;
      background: var(--panel-subtle);
      color: var(--muted);
      font-size: 11px;
      font-weight: 700;
      white-space: nowrap;
    }
    .evidence-panel-header {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 8px;
    }
    .evidence-panel-header h2 {
      margin: 0 0 3px;
      font-size: 16px;
    }
    .evidence-panel-header p {
      margin: 0;
      font-size: 12px;
    }
    .evidence-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 7px;
      margin: 10px 0;
    }
    .evidence-item {
      min-width: 0;
      min-height: 66px;
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      padding: 8px 9px;
      background: var(--panel-subtle);
    }
    .evidence-item span {
      display: block;
      color: var(--muted);
      font-size: 10px;
      text-transform: uppercase;
      margin-bottom: 4px;
    }
    .evidence-item strong {
      display: block;
      font-size: 15px;
      line-height: 1.15;
      overflow-wrap: anywhere;
    }
    .evidence-item small {
      display: block;
      margin-top: 3px;
      color: var(--muted);
      font-size: 10px;
      line-height: 1.25;
    }
    .model-context-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 7px;
      margin: 10px 0;
    }
    .model-context-card {
      min-width: 0;
      border: 1px solid var(--line);
      border-left: 3px solid var(--brand);
      border-radius: var(--radius-sm);
      padding: 8px 9px;
      background: var(--panel-subtle);
    }
    .model-context-card.conflict {
      border-color: var(--warning-line);
      border-left-color: var(--orange);
      background: var(--warning-bg);
    }
    .model-context-card > span {
      display: block;
      color: var(--muted);
      font-size: 10px;
      font-weight: 700;
      letter-spacing: .02em;
      text-transform: uppercase;
      margin-bottom: 4px;
    }
    .model-context-card strong {
      display: block;
      font-size: 14px;
      line-height: 1.2;
      overflow-wrap: anywhere;
    }
    .model-context-card small {
      display: block;
      margin-top: 4px;
      color: var(--muted);
      font-size: 10px;
      line-height: 1.3;
      overflow-wrap: anywhere;
    }
    .model-context-boundary {
      color: #78500a !important;
      font-weight: 700;
    }
    .comparison-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 6px;
      margin-top: 8px;
    }
    .comparison-item {
      border-top: 2px solid var(--brand);
      background: var(--panel-subtle);
      padding: 7px 8px;
      min-width: 0;
    }
    .comparison-item span {
      display: block;
      color: var(--muted);
      font-size: 10px;
      margin-bottom: 3px;
    }
    .comparison-item strong {
      display: block;
      font-size: 13px;
      overflow-wrap: anywhere;
    }
    .quality-list {
      display: grid;
      gap: 8px;
      margin-top: 8px;
    }
    .quality-row {
      display: grid;
      grid-template-columns: minmax(110px, 1fr) minmax(86px, 1.1fr) auto;
      align-items: center;
      gap: 8px;
      font-size: 11px;
    }
    .quality-row > span:first-child { color: var(--muted); }
    .quality-track {
      height: 6px;
      overflow: hidden;
      border-radius: 999px;
      background: #e6ece8;
    }
    .quality-fill {
      display: block;
      width: 0;
      height: 100%;
      border-radius: inherit;
      background: var(--brand);
      transition: width .18s ease;
    }
    .quality-fill.partial { background: var(--orange); }
    .quality-value { font-weight: 700; white-space: nowrap; }
    .provenance-list {
      display: grid;
      gap: 6px;
      margin: 8px 0 0;
    }
    .provenance-row {
      display: grid;
      grid-template-columns: 92px minmax(0, 1fr);
      gap: 8px;
      padding-top: 6px;
      border-top: 1px solid var(--line);
      font-size: 11px;
    }
    .provenance-row dt { color: var(--muted); }
    .provenance-row dd { margin: 0; overflow-wrap: anywhere; }
    .map-heading-copy { min-width: 0; }
    .map-heading-copy p { overflow-wrap: anywhere; }
    .map-status {
      display: flex;
      align-items: center;
      gap: 7px;
      margin-top: 4px;
      color: var(--muted);
      font-size: 11px;
    }
    .map-status-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--green);
      flex: 0 0 auto;
    }
    .map-status-dot.weak { background: var(--orange); }
    .map-status-dot.blocked { background: var(--red); }
    .map-detail-status {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 3px 7px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel-subtle);
      color: var(--muted);
      font-size: 10px;
      font-weight: 700;
      white-space: nowrap;
    }
    .marker-sample {
      width: 12px;
      height: 12px;
      border: 2px solid #fff;
      border-radius: 50%;
      box-shadow: 0 0 0 1px var(--line-strong);
      background: var(--blue);
      flex: 0 0 auto;
    }
    .marker-sample.hotspot {
      width: 14px;
      height: 14px;
      background: var(--red);
    }
    .facility-cluster-shell,
    .facility-marker-shell {
      background: transparent;
      border: 0;
    }
    .facility-cluster {
      width: 30px;
      height: 30px;
      display: grid;
      place-items: center;
      border: 2px solid #fff;
      border-radius: 50%;
      background: var(--blue);
      color: #fff;
      box-shadow: 0 0 0 2px rgba(40, 103, 184, .32), 0 5px 14px rgba(21, 36, 31, .2);
      font-size: 11px;
      font-weight: 800;
    }
    .facility-symbol {
      position: relative;
      width: 24px;
      height: 24px;
      display: block;
      border: 2px solid #fff;
      border-radius: 50%;
      box-shadow: 0 0 0 1px rgba(21, 36, 31, .3), 0 4px 10px rgba(21, 36, 31, .18);
      background: var(--blue);
    }
    .facility-symbol.healthcare::before,
    .facility-symbol.healthcare::after {
      content: "";
      position: absolute;
      left: 50%;
      top: 50%;
      width: 11px;
      height: 3px;
      border-radius: 1px;
      background: #fff;
      transform: translate(-50%, -50%);
    }
    .facility-symbol.healthcare::after { transform: translate(-50%, -50%) rotate(90deg); }
    .facility-symbol.clinic { background: #2867b8; }
    .facility-symbol.clinic::before,
    .facility-symbol.clinic::after {
      content: "";
      position: absolute;
      left: 50%;
      top: 50%;
      width: 11px;
      height: 3px;
      border-radius: 1px;
      background: #fff;
      transform: translate(-50%, -50%);
    }
    .facility-symbol.clinic::after { transform: translate(-50%, -50%) rotate(90deg); }
    .facility-symbol.hospital { background: #b83232; border-radius: 5px; }
    .facility-symbol.hospital::before {
      content: "H";
      position: absolute;
      inset: 0;
      display: grid;
      place-items: center;
      color: #fff;
      font-size: 13px;
      font-weight: 900;
    }
    .facility-symbol.school { background: #7a5a2d; border-radius: 4px; }
    .facility-symbol.school::before {
      content: "";
      position: absolute;
      left: 3px;
      top: 4px;
      width: 14px;
      height: 5px;
      border: 2px solid #fff;
      border-top-width: 4px;
    }
    .facility-symbol.school::after {
      content: "";
      position: absolute;
      left: 5px;
      bottom: 3px;
      width: 3px;
      height: 6px;
      background: #fff;
      box-shadow: 6px 0 0 #fff;
    }
    .facility-symbol.shelter_candidate { background: var(--green); border-radius: 4px; }
    .facility-symbol.shelter_candidate::before {
      content: "";
      position: absolute;
      left: 3px;
      top: 2px;
      width: 14px;
      height: 14px;
      border-left: 3px solid #fff;
      border-top: 3px solid #fff;
      transform: rotate(45deg);
    }
    .facility-symbol.shelter_candidate::after {
      content: "";
      position: absolute;
      left: 6px;
      bottom: 3px;
      width: 8px;
      height: 9px;
      background: #fff;
    }
    .facility-symbol.emergency_service {
      border-radius: 5px;
      background: var(--red);
      transform: rotate(45deg) scale(.82);
    }
    .facility-symbol.emergency_service::before {
      content: "!";
      position: absolute;
      inset: 0;
      display: grid;
      place-items: center;
      color: #fff;
      font-size: 15px;
      font-weight: 900;
      transform: rotate(-45deg);
    }
    .facility-symbol.community_facility { background: var(--violet); }
    .facility-symbol.community_facility::before {
      content: "";
      position: absolute;
      left: 5px;
      top: 6px;
      width: 4px;
      height: 4px;
      border-radius: 50%;
      background: #fff;
      box-shadow: 6px 0 0 #fff, 3px 6px 0 1px #fff;
    }
    .facility-legend-row {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .facility-legend-row .facility-symbol {
      width: 16px;
      height: 16px;
      transform: scale(.75);
      transform-origin: center;
      box-shadow: none;
    }
    .sar-evidence-drawer,
    .technical-provenance {
      border: 1px solid var(--line);
      border-radius: var(--radius-md);
      background: var(--panel-subtle);
      overflow: hidden;
    }
    .sar-evidence-drawer > summary,
    .technical-provenance > summary {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      min-height: 36px;
      padding: 7px 9px;
      cursor: pointer;
      color: var(--ink);
      font-size: 12px;
      font-weight: 800;
      list-style: none;
    }
    .sar-evidence-drawer > summary::-webkit-details-marker,
    .technical-provenance > summary::-webkit-details-marker { display: none; }
    .sar-evidence-drawer > summary::after,
    .technical-provenance > summary::after {
      content: "+";
      color: var(--brand);
      font-size: 16px;
    }
    .sar-evidence-drawer[open] > summary::after,
    .technical-provenance[open] > summary::after { content: "-"; }
    .sar-drawer-body { padding: 0 9px 9px; }
    .sar-acquisition-grid {
      display: grid;
      grid-template-columns: 1fr 72px 1fr;
      gap: 6px;
      align-items: stretch;
    }
    .sar-acquisition-card,
    .sar-change-card {
      min-width: 0;
      padding: 7px;
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      background: var(--panel);
    }
    .sar-acquisition-card span,
    .sar-change-card span {
      display: block;
      color: var(--muted);
      font-size: 9px;
      text-transform: uppercase;
    }
    .sar-acquisition-card strong,
    .sar-change-card strong {
      display: block;
      margin-top: 3px;
      font-size: 11px;
      line-height: 1.25;
      overflow-wrap: anywhere;
    }
    .sar-change-card { text-align: center; background: var(--brand-soft); }
    .sar-bar-list { display: grid; gap: 6px; margin-top: 8px; }
    .sar-bar-row { display: grid; grid-template-columns: 82px minmax(0, 1fr) 48px; gap: 6px; align-items: center; font-size: 10px; }
    .sar-bar-row > span:first-child { color: var(--muted); }
    .sar-bar-track { height: 6px; border-radius: 999px; background: #e5ece8; overflow: hidden; }
    .sar-bar-fill { display: block; width: 0; height: 100%; background: var(--brand); border-radius: inherit; }
    .sar-warning { margin: 8px 0 0; color: #78500a; font-size: 10px; line-height: 1.35; }
    .provenance-summary-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; margin-bottom: 8px; }
    .provenance-status-card { min-width: 0; padding: 7px; border: 1px solid var(--line); border-radius: var(--radius-sm); background: var(--panel-subtle); }
    .provenance-status-card span { display: block; color: var(--muted); font-size: 9px; text-transform: uppercase; }
    .provenance-status-card strong { display: block; margin-top: 3px; font-size: 11px; overflow-wrap: anywhere; }
    .technical-provenance .provenance-list { padding: 0 9px 9px; }
    body.judge-mode .judge-secondary,
    body.judge-mode [data-dashboard-section="context-readiness-panel"],
    body.judge-mode #local-data-library-panel,
    body.judge-mode .report-section pre,
    body.judge-mode .app-footer { display: none !important; }
    body.judge-mode .dashboard-workspace {
      grid-template-columns: minmax(200px, 230px) minmax(560px, 1fr) minmax(360px, 410px);
    }
    body.judge-mode .control-panel { overflow: hidden; }
    body.judge-mode .decision-panel { overflow-y: auto; }
    body.judge-mode .report-section { padding-bottom: 12px; }
    .section-eyebrow {
      color: var(--muted);
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
    }
    .control-context {
      display: grid;
      gap: 5px;
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      background: var(--panel-subtle);
      padding: 8px 9px;
      font-size: 11px;
      color: var(--muted);
    }
    .control-context strong { color: var(--ink); }
    .toolbar { flex-wrap: wrap; }
    [hidden] { display: none !important; }
    @media (max-width: 1300px) {
      .leaflet-tooltip.subdistrict-label {
        width: 54px;
        font-size: 8px;
        line-height: 1.05;
      }
    }
    @media (max-width: 1100px) {
      .kpi-strip { grid-template-columns: repeat(4, minmax(140px, 1fr)); }
      .dashboard-workspace,
      body.judge-mode .dashboard-workspace {
        grid-template-columns: 280px minmax(520px, 1fr);
        height: auto;
        min-height: 0;
      }
      .decision-panel {
        grid-column: 1 / -1;
        max-height: none;
      }
    }
    @media (max-width: 900px) {
      .app-shell { padding: 10px; }
      .app-header { grid-template-columns: 1fr; }
      .brand-copy h1 { white-space: normal; }
      .status-row { justify-content: flex-start; }
      .header-side { justify-items: start; }
      .kpi-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .dashboard-workspace,
      body.judge-mode .dashboard-workspace {
        display: flex;
        flex-direction: column;
        height: auto;
        min-height: 0;
      }
      .mode-warning { grid-template-columns: 1fr; }
      .mode-warning strong,
      .mode-warning .warning-status { justify-self: start; }
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
      .model-context-grid {
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
          <h1 data-i18n="app.title">FloodGuard Decision Dashboard</h1>
          <p id="header-subtitle">Judge-demo command center for fixture-backed local prioritization. Not an official warning.</p>
        </div>
      </div>
      <div class="header-side">
        <div class="status-row" aria-label="Dashboard status">
          <span class="status-chip demo" id="status-dataset">Fixture demo</span>
          <span class="status-chip warn" data-i18n="status.nonOperational">Non-operational</span>
          <span class="status-chip blocked" id="status-validation">Real validation blocked</span>
          <span class="timestamp" data-i18n="status.static">Static HTML | embedded data | no backend</span>
        </div>
        <div class="display-controls" aria-label="Display controls">
          <div class="segmented-control" role="group" aria-label="Language">
            <button class="segment-button" id="language-en" type="button" aria-pressed="true">EN</button>
            <button class="segment-button" id="language-th" type="button" aria-pressed="false">TH</button>
          </div>
          <button class="judge-toggle" id="judge-mode-toggle" type="button" aria-pressed="false" data-i18n="judge.enter">Judge mode</button>
        </div>
      </div>
    </header>

    <section class="kpi-strip" data-dashboard-section="kpi-strip" aria-label="Priority KPIs">
      <div class="kpi-card"><span class="label" data-i18n="kpi.selected">Selected</span><span class="value" id="panel-subdistrict">__TOP_SUBDISTRICT__</span><span class="kpi-note" id="panel-subdistrict-name">__TOP_NAME__</span></div>
      <div class="kpi-card"><span class="label" data-i18n="kpi.fpps">FPPS</span><span class="value" id="panel-fpps">__TOP_FPPS__</span><span class="kpi-note" data-i18n="kpi.scoreNote">0-100 priority score</span></div>
      <div class="kpi-card"><span class="label" data-i18n="kpi.action">Action class</span><span class="value" id="panel-class">__TOP_CLASS__</span><span class="kpi-note" id="panel-action-label">__TOP_ACTION_LABEL__</span></div>
      <div class="kpi-card"><span class="label" data-i18n="kpi.confidence">Confidence</span><span class="value" id="panel-confidence">__TOP_CONFIDENCE__</span><span class="kpi-note" id="panel-confidence-note">fixture class</span></div>
      <div class="kpi-card"><span class="label" id="panel-access-label" data-i18n="kpi.access">30-min access loss</span><span class="value" id="panel-baseline-access">__TOP_BASELINE_ACCESS__</span><span class="kpi-note" id="panel-access-note">baseline people</span></div>
      <div class="kpi-card"><span class="label" data-i18n="kpi.equity">Equity gap</span><span class="value" id="panel-baseline-equity">__TOP_BASELINE_EQUITY__</span><span class="kpi-note" data-i18n="common.ratio">ratio</span></div>
      <div class="kpi-card"><span class="label" id="panel-kpi-seven-label">Shelter scenario</span><span class="value"><span class="delta-badge" id="panel-temp-delta">__TOP_TEMP_DELTA__</span></span><span class="kpi-note" id="panel-kpi-seven-note">30-min access change</span></div>
      <div class="kpi-card"><span class="label" id="panel-kpi-eight-label">Road closure</span><span class="value"><span class="delta-badge" id="panel-road-delta">__TOP_ROAD_DELTA__</span></span><span class="kpi-note" id="panel-kpi-eight-note">stress-case change</span></div>
    </section>

    <div class="mode-warning" id="mode-warning" role="status" aria-live="polite">
      <strong id="mode-warning-title">Fixture demonstration</strong>
      <span id="mode-warning-text">Synthetic decision inputs demonstrate the workflow. They do not establish real flood accuracy.</span>
      <span class="warning-status" id="mode-warning-status">Not official</span>
    </div>

    <section class="dashboard-workspace" data-dashboard-section="dashboard-workspace" aria-label="FloodGuard judge-demo workspace">
      <aside class="control-panel" data-dashboard-section="control-panel">
        <div class="panel-title">
          <h2 id="controls-title" data-i18n="controls.title">Controls &amp; Scenario</h2>
          <span id="controls-subtitle" data-i18n="controls.subtitle">Scenario setup</span>
        </div>
        <div class="control-stack">
          <div>
            <label class="control-label" for="dataset-mode-select" data-i18n="controls.dataset">Dataset mode</label>
            <select id="dataset-mode-select">
              <option value="fixture_demo">Fixture demo</option>
              <option value="mae_sai_weak_reference">Mae Sai weak-reference candidate</option>
              <option value="metadata_blocker_view">Metadata/blocker view</option>
            </select>
          </div>
          <div>
            <label class="control-label" for="subdistrict-select" data-i18n="controls.subdistrict">Subdistrict</label>
            <select id="subdistrict-select"></select>
          </div>
          <div class="judge-secondary">
            <span class="control-label" data-i18n="controls.actionFilters">Action class filters</span>
            <div class="filter-row" id="action-class-filters" aria-label="Action class filters">
              <label><input class="action-filter" type="checkbox" value="A" checked> A</label>
              <label><input class="action-filter" type="checkbox" value="B" checked> B</label>
              <label><input class="action-filter" type="checkbox" value="C" checked> C</label>
              <label><input class="action-filter" type="checkbox" value="D" checked> D</label>
              <label><input class="action-filter" type="checkbox" value="E" checked> E</label>
            </div>
          </div>
          <div class="judge-secondary">
            <label class="control-label" for="scenario-select" data-i18n="controls.scenario">Scenario mode</label>
            <select id="scenario-select">
              <option value="baseline">baseline</option>
              <option value="temporary_shelter">temporary shelter delta</option>
              <option value="road_closure">road closure delta</option>
            </select>
          </div>
          <div class="control-context">
            <span class="section-eyebrow" data-i18n="controls.scope">Current evidence scope</span>
            <strong id="control-evidence-title">Synthetic fixture</strong>
            <span id="control-evidence-note">Scenario controls are available for the fixture workflow.</span>
          </div>
        </div>
        <div class="button-row judge-secondary" aria-label="Dashboard exports">
          <button id="download-current-brief" type="button" data-i18n="buttons.brief">Download current brief</button>
          <button id="download-filtered-geojson" type="button" data-i18n="buttons.geojson">Download filtered GeoJSON</button>
        </div>
        <div id="fixture-scenario-summary" class="judge-secondary">
        <h2 data-i18n="scenario.title">Scenario Summary</h2>
        <div class="summary-card-grid">
          <div class="summary-card" id="summary-best-intervention">
            <span class="label" data-i18n="scenario.best">Best intervention effect</span>
            <strong>__BEST_INTERVENTION_LABEL__</strong>
            <span>Temporary shelter: __BEST_INTERVENTION_DELTA__ people losing 30-min access</span>
          </div>
          <div class="summary-card" id="summary-worst-road-closure">
            <span class="label" data-i18n="scenario.worst">Worst road-closure stress case</span>
            <strong>__WORST_ROAD_CLOSURE_LABEL__</strong>
            <span>Road closure: __WORST_ROAD_CLOSURE_DELTA__ people losing 30-min access</span>
          </div>
        </div>
        </div>
        <div class="judge-secondary">
        <h2 data-i18n="controls.boundary">Evidence Boundary</h2>
        <p class="dataset-mode-note" id="dataset-mode-note">Fixture demo: synthetic priority, access, equity, and road-risk outputs. Use this mode to judge the decision-layer workflow, not real flood accuracy.</p>
        <div class="control-context">
          <strong data-i18n="controls.readFirst">Read This First</strong>
          <span data-i18n="controls.contextWarning">Context layers are not flood labels, observed closures, or agency warning products.</span>
          <span data-i18n="controls.validationWarning">Official validation remains blocked; weak-reference metrics stay candidate evidence.</span>
        </div>
        </div>
      </aside>

      <section class="map-panel" data-dashboard-section="map-panel" aria-label="FloodGuard map panel">
        <div class="map-heading">
          <div class="map-heading-copy">
            <h2 id="map-title">Fixture Priority Map</h2>
            <p id="map-subtitle">Synthetic priority polygons and road-risk segments from embedded GeoJSON.</p>
            <div class="map-status"><i class="map-status-dot" id="map-status-dot"></i><span id="map-status-text">Fixture-backed decision workflow</span><span class="map-detail-status" id="map-detail-status">Regional view</span></div>
          </div>
          <div class="toolbar" aria-label="Layer toggles">
            <label><input id="toggle-priority" type="checkbox" checked> <span data-i18n="layer.priority">Priority</span></label>
            <label><input id="toggle-roads" type="checkbox" checked> <span data-i18n="layer.roads">Road risk</span></label>
            <label><input id="toggle-facilities" type="checkbox" checked> <span data-i18n="layer.facilities">Facilities</span></label>
            <label><input id="toggle-hotspots" type="checkbox" checked> <span data-i18n="layer.hotspots">Access hotspots</span></label>
            <label><input id="toggle-focus" type="checkbox" checked> <span data-i18n="layer.focus">Focus selected</span></label>
          </div>
        </div>
        <div class="map-body">
          <div id="map"></div>
          <div class="map-legend" aria-label="Map legend">
            <div class="legend-group">
              <strong id="legend-primary-title">Action class</strong>
              <div class="legend-group" id="legend-primary-items">
                <span class="legend-item"><i class="swatch" style="background:#b73c3c"></i>A Protect Lives</span>
                <span class="legend-item"><i class="swatch" style="background:#d36a35"></i>B Routes</span>
                <span class="legend-item"><i class="swatch" style="background:#d8a629"></i>C Services</span>
                <span class="legend-item"><i class="swatch" style="background:#21835f"></i>D Resilience</span>
                <span class="legend-item"><i class="swatch" style="background:#6d5aa8"></i>E Monitor</span>
              </div>
            </div>
            <div class="legend-group">
              <strong id="legend-secondary-title">Scenario and road risk</strong>
              <div class="legend-group" id="legend-secondary-items">
                <span class="legend-item"><i class="swatch" style="background:#21835f"></i>Delta improves</span>
                <span class="legend-item"><i class="swatch" style="background:#b73c3c"></i>Delta worsens</span>
                <span class="legend-item"><i class="road-sample"></i>High road risk</span>
                <span class="legend-item"><i class="road-sample medium"></i>Medium road risk</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <aside class="decision-panel" data-dashboard-section="decision-panel">
        <section class="panel-section" id="decision-brief-panel">
          <div class="evidence-panel-header">
            <div>
              <span class="section-eyebrow" data-i18n="evidence.selectedUnit">Selected decision unit</span>
              <h2 id="panel-detail-title">__TOP_SUBDISTRICT__ / __TOP_NAME__</h2>
              <p id="panel-reason">__TOP_REASON__</p>
            </div>
            <div>
              <span class="class-pill" id="panel-detail-class">Class __TOP_CLASS__</span>
            </div>
          </div>
          <div class="evidence-grid" aria-label="Selected evidence metrics">
            <div class="evidence-item"><span data-i18n="evidence.flood">Flood evidence</span><strong id="panel-evidence-flood">unavailable</strong><small id="panel-evidence-flood-note">candidate probability</small></div>
            <div class="evidence-item"><span data-i18n="evidence.exposure">Expected exposure</span><strong id="panel-evidence-exposure">unavailable</strong><small id="panel-evidence-exposure-note">modeled proxy</small></div>
            <div class="evidence-item"><span data-i18n="evidence.access">30-min access loss</span><strong id="panel-detail-access">__TOP_BASELINE_ACCESS__</strong><small id="panel-evidence-access-note">modeled people</small></div>
            <div class="evidence-item"><span data-i18n="evidence.equity">Proxy equity gap</span><strong id="panel-detail-equity">__TOP_BASELINE_EQUITY__</strong><small id="panel-evidence-equity-note">ratio</small></div>
            <div class="evidence-item"><span data-i18n="evidence.roads">Road evidence</span><strong id="panel-evidence-roads">unavailable</strong><small id="panel-evidence-roads-note">candidate network risk</small></div>
            <div class="evidence-item"><span data-i18n="evidence.terrain">Terrain context</span><strong id="panel-evidence-terrain">unavailable</strong><small id="panel-evidence-terrain-note">DEM candidate coverage</small></div>
          </div>
          <div class="model-context-grid" id="model-context-panel" data-dashboard-section="model-context-panel" aria-label="Model pathway and historical context">
            <div class="model-context-card" id="modality-context-card">
              <span data-i18n="model.modality">Research fusion candidate</span>
              <strong id="panel-modality-used">unavailable</strong>
              <small id="panel-modality-reason" data-i18n="model.noFusion">No fusion decision metadata is available.</small>
              <small id="panel-modality-meta" data-i18n="model.noSource">Source and confidence unavailable.</small>
              <small class="model-context-boundary" data-i18n="model.sidecarBoundary">Research sidecar; not used by FPPS or action class.</small>
            </div>
            <div class="model-context-card" id="historical-context-card">
              <span data-i18n="model.historical">Historical susceptibility/context</span>
              <strong id="panel-historical-susceptibility">unavailable</strong>
              <small id="panel-historical-explanation" data-i18n="model.noHistorical">Historical context is unavailable for this reporting unit.</small>
              <small id="panel-historical-warning" data-i18n="model.noComparison">No plausibility comparison is available.</small>
              <small id="panel-historical-meta" data-i18n="model.noHistoricalMeta">Source, confidence, and calibration unavailable.</small>
              <small class="model-context-boundary" data-i18n="model.boundary">Not observed current flooding. Not a forecast.</small>
            </div>
          </div>
          <span class="section-eyebrow" data-i18n="evidence.comparison">Selected vs current dataset</span>
          <div class="comparison-grid" aria-label="Selected subdistrict comparison">
            <div class="comparison-item"><span data-i18n="evidence.rank">FPPS rank</span><strong id="comparison-rank">unavailable</strong></div>
            <div class="comparison-item"><span data-i18n="evidence.floodMedian">Flood vs median</span><strong id="comparison-flood">unavailable</strong></div>
            <div class="comparison-item"><span data-i18n="evidence.accessMax">Access vs maximum</span><strong id="comparison-access">unavailable</strong></div>
          </div>
          <div class="safety-note" id="panel-safety-note">Context only. Not flood detection. Not validation. Not an official warning.</div>
        </section>
        <section class="panel-section" id="source-quality-panel">
          <div class="panel-title"><h2 data-i18n="quality.title">Source Quality</h2><span id="quality-confidence">candidate</span></div>
          <div class="quality-list">
            <div class="quality-row"><span data-i18n="quality.population">Population coverage</span><div class="quality-track"><i class="quality-fill" id="quality-population-fill"></i></div><strong class="quality-value" id="quality-population-value">unavailable</strong></div>
            <div class="quality-row"><span data-i18n="quality.road">Road snap coverage</span><div class="quality-track"><i class="quality-fill" id="quality-road-fill"></i></div><strong class="quality-value" id="quality-road-value">unavailable</strong></div>
            <div class="quality-row"><span data-i18n="quality.dem">DEM coverage</span><div class="quality-track"><i class="quality-fill" id="quality-dem-fill"></i></div><strong class="quality-value" id="quality-dem-value">unavailable</strong></div>
            <div class="quality-row"><span data-i18n="quality.reference">Reference alignment</span><div class="quality-track"><i class="quality-fill partial" id="quality-reference-fill"></i></div><strong class="quality-value" id="quality-reference-value">unavailable</strong></div>
          </div>
        </section>
        <section class="panel-section" id="sar-evidence-panel">
          <details class="sar-evidence-drawer" id="sar-evidence-drawer">
            <summary><span data-i18n="sar.title">Sentinel-1 evidence</span><span class="dataset-badge" id="sar-evidence-status">weak reference</span></summary>
            <div class="sar-drawer-body">
              <div class="sar-acquisition-grid">
                <div class="sar-acquisition-card"><span data-i18n="sar.pre">Pre-event</span><strong id="sar-pre-date">unavailable</strong><small id="sar-pre-product">unavailable</small></div>
                <div class="sar-change-card"><span data-i18n="sar.change">Change</span><strong id="sar-change-score">unavailable</strong></div>
                <div class="sar-acquisition-card"><span data-i18n="sar.post">Post-event</span><strong id="sar-post-date">unavailable</strong><small id="sar-post-product">unavailable</small></div>
              </div>
              <div class="sar-bar-list">
                <div class="sar-bar-row"><span data-i18n="sar.mean">Mean probability</span><div class="sar-bar-track"><i class="sar-bar-fill" id="sar-mean-fill"></i></div><strong id="sar-mean-value">unavailable</strong></div>
                <div class="sar-bar-row"><span data-i18n="sar.p90">P90 probability</span><div class="sar-bar-track"><i class="sar-bar-fill" id="sar-p90-fill"></i></div><strong id="sar-p90-value">unavailable</strong></div>
                <div class="sar-bar-row"><span data-i18n="sar.binary">Binary share</span><div class="sar-bar-track"><i class="sar-bar-fill" id="sar-binary-fill"></i></div><strong id="sar-binary-value">unavailable</strong></div>
              </div>
              <p class="sar-warning" data-i18n="sar.warning">Derived ADM3 statistics only. Weak-reference candidate, not official validation, not field validated, and not an official warning.</p>
            </div>
          </details>
        </section>
        <section class="panel-section mae-sai-weak-card" id="mae-sai-weak-reference-card">
          <div class="panel-title"><h2 data-i18n="provenance.title">Provenance</h2><span id="provenance-status">embedded</span></div>
          <div class="provenance-summary-grid">
            <div class="provenance-status-card"><span data-i18n="provenance.time">Source time</span><strong id="provenance-time">unavailable</strong></div>
            <div class="provenance-status-card"><span data-i18n="provenance.reference">Reference</span><strong id="provenance-reference">unavailable</strong></div>
            <div class="provenance-status-card"><span data-i18n="provenance.scope">Scope</span><strong id="provenance-scope">unavailable</strong></div>
          </div>
          <details class="technical-provenance" id="technical-provenance">
            <summary data-i18n="provenance.technical">Technical provenance</summary>
            <dl class="provenance-list">
              <div class="provenance-row"><dt data-i18n="sar.pre">Pre Sentinel-1</dt><dd id="provenance-pre">unavailable</dd></div>
              <div class="provenance-row"><dt data-i18n="sar.post">Post Sentinel-1</dt><dd id="provenance-post">unavailable</dd></div>
              <div class="provenance-row"><dt data-i18n="provenance.assumptions">Assumptions</dt><dd id="provenance-assumptions">unavailable</dd></div>
            </dl>
          </details>
        </section>
        <section class="panel-section" data-dashboard-section="context-readiness-panel">
          <div class="context-preview-heading">
            <h2 data-i18n="context.title">Context Assets</h2>
            <span data-i18n="context.note">preview only; not flood labels</span>
          </div>
          <div class="context-preview-grid">
            <div>
              <h3 data-i18n="context.sar">Sentinel-1 SAR Context</h3>
              <div class="sar-context" id="sentinel1-sar-context">
                __SENTINEL1_CONTEXT_HTML__
              </div>
            </div>
            <div>
              <h3 data-i18n="context.dem">DEM Terrain Context</h3>
              <div class="dem-context" id="dem-terrain-context">
                __DEM_CONTEXT_HTML__
              </div>
            </div>
            <div>
              <h3 data-i18n="context.optical">THEOS-2 Optical Context</h3>
              <div class="theos2-context" id="theos2-context">
                __THEOS2_CONTEXT_HTML__
              </div>
            </div>
          </div>
        </section>
        <section class="panel-section" id="local-data-library-panel">
          <div class="panel-title">
            <h2 data-i18n="library.title">Local Data Library</h2>
            <span data-i18n="library.gated">processing gated</span>
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
        <div class="report-heading"><h2 data-i18n="report.validation">Validation Summary</h2><span id="report-validation-scope">Fixture Metrics</span></div>
        <div class="validation-metric-grid">__VALIDATION_METRIC_CARDS__</div>
        <p class="report-notes" id="report-validation-note">Toy metrics are synthetic fixtures only. Real flood validation remains blocked until legal reference masks and file-level gates pass.</p>
        <pre id="validation-summary-pre">__VALIDATION_SUMMARY__</pre>
      </article>
      <article id="action-brief">
        <div class="report-heading"><h2 data-i18n="report.brief">Action Brief</h2><span data-i18n="report.detailed">Detailed</span></div>
        <div class="brief-summary">
          <strong id="report-brief-title">__TOP_SUBDISTRICT__ / __TOP_NAME__ (Class __TOP_CLASS__)</strong>
          <ul>
            <li id="report-brief-focus">Immediate local action focus: __TOP_REASON__</li>
            <li id="report-brief-access">Access-loss impact: __TOP_BASELINE_ACCESS__ people losing 30-minute access.</li>
            <li id="report-brief-warning">This is not an official warning. Use with local assessment and official advisories.</li>
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
    const maeSaiPriorityData = __MAE_SAI_PRIORITY_JSON__;
    const maeSaiRoadRiskData = __MAE_SAI_ROAD_JSON__;
    const maeSaiFacilityData = __MAE_SAI_FACILITY_JSON__;
    const maeSaiAccessHotspotData = __MAE_SAI_ACCESS_HOTSPOT_JSON__;
    const maeSaiContextQuality = __MAE_SAI_CONTEXT_QUALITY_JSON__;
    const maeSaiSarContext = __MAE_SAI_SAR_CONTEXT_JSON__;
    const maeSaiBriefsBySubdistrict = __MAE_SAI_BRIEFS_JSON__;
    const maeSaiWeakReferenceSummary = __MAE_SAI_WEAK_JSON__;
    const theos2PreviewData = __THEOS2_JSON__;
    const sentinel1QuicklookData = __SENTINEL1_QUICKLOOK_JSON__;
    const demQuicklookData = __DEM_QUICKLOOK_JSON__;
    const localDataLibrarySummary = __LOCAL_DATA_JSON__;
    const fixtureValidationMetrics = __FIXTURE_VALIDATION_METRICS_JSON__;
    const fixtureValidationSummary = __FIXTURE_VALIDATION_SUMMARY_JSON__;
    const maeSaiValidationSummary = __MAE_SAI_VALIDATION_SUMMARY_JSON__;
    const emptyFeatureCollection = { type: 'FeatureCollection', features: [] };
    const translations = {
      en: {
        'app.title': 'FloodGuard Decision Dashboard',
        'status.nonOperational': 'Non-operational',
        'status.static': 'Static HTML | embedded data | no backend',
        'judge.enter': 'Judge mode',
        'judge.exit': 'Exit judge mode',
        'kpi.selected': 'Selected',
        'kpi.fpps': 'FPPS',
        'kpi.scoreNote': '0-100 priority score',
        'kpi.action': 'Action class',
        'kpi.confidence': 'Confidence',
        'kpi.access': '30-min access loss',
        'kpi.equity': 'Equity gap',
        'common.ratio': 'ratio',
        'controls.title': 'Controls & Scenario',
        'controls.subtitle': 'Scenario setup',
        'controls.presentationTitle': 'Dataset & Selection',
        'controls.presentationSubtitle': 'Judge presentation',
        'controls.dataset': 'Dataset mode',
        'controls.subdistrict': 'Subdistrict',
        'controls.actionFilters': 'Action class filters',
        'controls.scenario': 'Scenario mode',
        'controls.scope': 'Current evidence scope',
        'controls.boundary': 'Evidence Boundary',
        'controls.readFirst': 'Read This First',
        'controls.contextWarning': 'Context layers are not flood labels, observed closures, or agency warning products.',
        'controls.validationWarning': 'Official validation remains blocked; weak-reference metrics stay candidate evidence.',
        'scenario.title': 'Scenario Summary',
        'scenario.best': 'Best intervention effect',
        'scenario.worst': 'Worst road-closure stress case',
        'buttons.brief': 'Download current brief',
        'buttons.geojson': 'Download filtered GeoJSON',
        'layer.priority': 'Priority',
        'layer.roads': 'Road risk',
        'layer.facilities': 'Facilities',
        'layer.hotspots': 'Access hotspots',
        'layer.focus': 'Focus selected',
        'evidence.selectedUnit': 'Selected decision unit',
        'evidence.flood': 'Flood evidence',
        'evidence.exposure': 'Expected exposure',
        'evidence.access': '30-min access loss',
        'evidence.equity': 'Proxy equity gap',
        'evidence.roads': 'Road evidence',
        'evidence.terrain': 'Terrain context',
        'evidence.comparison': 'Selected vs current dataset',
        'evidence.rank': 'FPPS rank',
        'evidence.floodMedian': 'Flood vs median',
        'evidence.accessMax': 'Access vs maximum',
        'model.modality': 'Research fusion candidate',
        'model.historical': 'Historical susceptibility/context',
        'model.boundary': 'Not observed current flooding. Not a forecast.',
        'model.noFusion': 'No fusion decision metadata is available.',
        'model.noSource': 'Source and confidence unavailable.',
        'model.noHistorical': 'Historical context is unavailable for this reporting unit.',
        'model.noComparison': 'No plausibility comparison is available.',
        'model.noHistoricalMeta': 'Source, confidence, and calibration unavailable.',
        'model.decisionWithheld': 'Decision imagery is withheld in metadata/blocker view.',
        'model.historicalWithheld': 'Historical context values are withheld in metadata/blocker view.',
        'model.gatesOnly': 'Metadata and readiness gates only.',
        'model.noComparisonView': 'No plausibility comparison is made in this view.',
        'model.existingSar': 'Existing Sentinel-1 candidate path; no aligned, quality-qualified optical fusion input.',
        'model.noMode': 'No observation-modality decision metadata is available.',
        'model.sourceTime': 'Source time',
        'model.confidence': 'confidence',
        'model.calibration': 'calibration',
        'model.sidecarBoundary': 'Research sidecar; not used by FPPS or action class.',
        'quality.title': 'Source Quality',
        'quality.population': 'Population coverage',
        'quality.road': 'Road snap coverage',
        'quality.dem': 'DEM coverage',
        'quality.reference': 'Reference alignment',
        'sar.title': 'Sentinel-1 evidence',
        'sar.pre': 'Pre-event',
        'sar.post': 'Post-event',
        'sar.change': 'Change',
        'sar.mean': 'Mean probability',
        'sar.p90': 'P90 probability',
        'sar.binary': 'Binary share',
        'sar.warning': 'Derived ADM3 statistics only. Weak-reference candidate, not official validation, not field validated, and not an official warning.',
        'provenance.title': 'Provenance',
        'provenance.time': 'Source time',
        'provenance.reference': 'Reference',
        'provenance.scope': 'Scope',
        'provenance.technical': 'Technical provenance',
        'provenance.assumptions': 'Assumptions',
        'context.title': 'Context Assets',
        'context.note': 'preview only; not flood labels',
        'context.sar': 'Sentinel-1 SAR Context',
        'context.dem': 'DEM Terrain Context',
        'context.optical': 'THEOS-2 Optical Context',
        'library.title': 'Local Data Library',
        'library.gated': 'processing gated',
        'report.validation': 'Validation Summary',
        'report.brief': 'Action Brief',
        'report.detailed': 'Detailed',
        'dataset.fixture': 'Fixture demo',
        'dataset.mae': 'Mae Sai weak-reference candidate',
        'dataset.blocker': 'Metadata/blocker view',
        'scenario.baseline': 'baseline',
        'scenario.shelter': 'temporary shelter delta',
        'scenario.road': 'road closure delta',
        'map.regional': 'Regional: priority roads + facility clusters',
        'map.detail': 'Selected-area detail',
        'map.fixtureDetail': 'Fixture map detail',
        'map.reportingOnly': 'Reporting boundaries only',
        'map.roadSegments': 'road segments',
        'map.priorityRoads': 'priority roads',
        'map.selectedRoads': 'selected-area roads',
        'map.facilityClusters': 'facility clusters',
        'map.facilities': 'facilities',
        'common.unavailable': 'unavailable',
        'common.withheld': 'withheld',
        'common.gated': 'gated',
        'common.of': 'of'
      },
      th: {
        'app.title': 'แดชบอร์ดการตัดสินใจ FloodGuard',
        'status.nonOperational': 'ไม่ใช่ระบบปฏิบัติการจริง',
        'status.static': 'HTML แบบสแตติก | ข้อมูลฝังในไฟล์ | ไม่มีแบ็กเอนด์',
        'judge.enter': 'โหมดนำเสนอ',
        'judge.exit': 'ออกจากโหมดนำเสนอ',
        'kpi.selected': 'พื้นที่ที่เลือก',
        'kpi.fpps': 'คะแนน FPPS',
        'kpi.scoreNote': 'คะแนนลำดับความสำคัญ 0-100',
        'kpi.action': 'ระดับการปฏิบัติ',
        'kpi.confidence': 'ความเชื่อมั่น',
        'kpi.access': 'ผู้เสียการเข้าถึงใน 30 นาที',
        'kpi.equity': 'ช่องว่างความเสมอภาค',
        'common.ratio': 'อัตราส่วน',
        'controls.title': 'ตัวควบคุมและสถานการณ์',
        'controls.subtitle': 'ตั้งค่าการแสดงผล',
        'controls.presentationTitle': 'ชุดข้อมูลและพื้นที่',
        'controls.presentationSubtitle': 'โหมดนำเสนอสำหรับกรรมการ',
        'controls.dataset': 'ชุดข้อมูล',
        'controls.subdistrict': 'ตำบล',
        'controls.actionFilters': 'ตัวกรองระดับการปฏิบัติ',
        'controls.scenario': 'สถานการณ์จำลอง',
        'controls.scope': 'ขอบเขตหลักฐานปัจจุบัน',
        'controls.boundary': 'ขอบเขตการใช้หลักฐาน',
        'controls.readFirst': 'อ่านก่อนใช้งาน',
        'controls.contextWarning': 'ชั้นข้อมูลบริบทไม่ใช่ป้ายกำกับน้ำท่วม การปิดถนนที่สังเกตจริง หรือผลิตภัณฑ์เตือนภัยของหน่วยงาน',
        'controls.validationWarning': 'การตรวจสอบอย่างเป็นทางการยังไม่สมบูรณ์ ตัวชี้วัดจากข้อมูลอ้างอิงแบบอ่อนเป็นเพียงหลักฐานผู้สมัคร',
        'scenario.title': 'สรุปสถานการณ์',
        'scenario.best': 'ผลการแทรกแซงที่ดีที่สุด',
        'scenario.worst': 'กรณีทดสอบการปิดถนนที่รุนแรงที่สุด',
        'buttons.brief': 'ดาวน์โหลดสรุปพื้นที่',
        'buttons.geojson': 'ดาวน์โหลด GeoJSON ที่กรองแล้ว',
        'layer.priority': 'ลำดับความสำคัญ',
        'layer.roads': 'ความเสี่ยงถนน',
        'layer.facilities': 'สถานที่สำคัญ',
        'layer.hotspots': 'จุดสูญเสียการเข้าถึง',
        'layer.focus': 'เน้นพื้นที่ที่เลือก',
        'evidence.selectedUnit': 'หน่วยตัดสินใจที่เลือก',
        'evidence.flood': 'หลักฐานน้ำท่วม',
        'evidence.exposure': 'ประชากรที่อาจได้รับผลกระทบ',
        'evidence.access': 'การสูญเสียการเข้าถึง 30 นาที',
        'evidence.equity': 'ช่องว่างความเสมอภาคโดยประมาณ',
        'evidence.roads': 'หลักฐานด้านถนน',
        'evidence.terrain': 'บริบทภูมิประเทศ',
        'evidence.comparison': 'เปรียบเทียบกับชุดข้อมูลปัจจุบัน',
        'evidence.rank': 'อันดับ FPPS',
        'evidence.floodMedian': 'น้ำท่วมเทียบค่ามัธยฐาน',
        'evidence.accessMax': 'การเข้าถึงเทียบค่าสูงสุด',
        'model.modality': 'ผลการผสานข้อมูลเพื่อการวิจัย',
        'model.historical': 'ความไวต่อน้ำท่วมในอดีต/บริบท',
        'model.boundary': 'ไม่ใช่การสังเกตน้ำท่วมปัจจุบัน และไม่ใช่การพยากรณ์',
        'model.noFusion': 'ไม่มีข้อมูลการตัดสินใจจากการผสานข้อมูล',
        'model.noSource': 'ไม่มีข้อมูลแหล่งที่มาและความเชื่อมั่น',
        'model.noHistorical': 'ไม่มีบริบทน้ำท่วมในอดีตสำหรับหน่วยรายงานนี้',
        'model.noComparison': 'ไม่มีข้อมูลเปรียบเทียบความสมเหตุสมผล',
        'model.noHistoricalMeta': 'ไม่มีข้อมูลแหล่งที่มา ความเชื่อมั่น และการสอบเทียบ',
        'model.decisionWithheld': 'ซ่อนข้อมูลภาพประกอบการตัดสินใจในมุมมองข้อมูลกำกับ/ข้อจำกัด',
        'model.historicalWithheld': 'ซ่อนค่าบริบทในอดีตในมุมมองข้อมูลกำกับ/ข้อจำกัด',
        'model.gatesOnly': 'แสดงเฉพาะข้อมูลกำกับและเงื่อนไขความพร้อม',
        'model.noComparisonView': 'ไม่มีการเปรียบเทียบความสมเหตุสมผลในมุมมองนี้',
        'model.existingSar': 'ใช้เส้นทาง Sentinel-1 เดิม โดยไม่มีข้อมูลภาพเชิงแสงที่ผ่านเกณฑ์คุณภาพและการจัดแนว',
        'model.noMode': 'ไม่มีข้อมูลรูปแบบการสังเกตที่ใช้ตัดสินใจ',
        'model.sourceTime': 'เวลาของแหล่งข้อมูล',
        'model.confidence': 'ความเชื่อมั่น',
        'model.calibration': 'การสอบเทียบ',
        'model.sidecarBoundary': 'ข้อมูลประกอบการวิจัย ไม่ได้นำไปใช้คำนวณ FPPS หรือระดับการปฏิบัติ',
        'quality.title': 'คุณภาพแหล่งข้อมูล',
        'quality.population': 'ความครอบคลุมประชากร',
        'quality.road': 'ความครอบคลุมการเชื่อมถนน',
        'quality.dem': 'ความครอบคลุม DEM',
        'quality.reference': 'ความสอดคล้องกับข้อมูลอ้างอิง',
        'sar.title': 'หลักฐาน Sentinel-1',
        'sar.pre': 'ก่อนเหตุการณ์',
        'sar.post': 'หลังเหตุการณ์',
        'sar.change': 'การเปลี่ยนแปลง',
        'sar.mean': 'ความน่าจะเป็นเฉลี่ย',
        'sar.p90': 'ความน่าจะเป็น P90',
        'sar.binary': 'สัดส่วนพื้นที่เกินเกณฑ์',
        'sar.warning': 'เป็นสถิติระดับตำบลจากข้อมูลอ้างอิงแบบอ่อนเท่านั้น ไม่ใช่การตรวจสอบอย่างเป็นทางการ ไม่ได้ตรวจสอบภาคสนาม และไม่ใช่คำเตือนภัยอย่างเป็นทางการ',
        'provenance.title': 'ที่มาของข้อมูล',
        'provenance.time': 'เวลาของข้อมูล',
        'provenance.reference': 'ข้อมูลอ้างอิง',
        'provenance.scope': 'ขอบเขตการประมวลผล',
        'provenance.technical': 'รายละเอียดทางเทคนิค',
        'provenance.assumptions': 'สมมติฐาน',
        'context.title': 'ข้อมูลบริบท',
        'context.note': 'ตัวอย่างเท่านั้น ไม่ใช่ป้ายกำกับน้ำท่วม',
        'context.sar': 'บริบท SAR จาก Sentinel-1',
        'context.dem': 'บริบทภูมิประเทศจาก DEM',
        'context.optical': 'บริบทภาพถ่ายจาก THEOS-2',
        'library.title': 'คลังข้อมูลภายในเครื่อง',
        'library.gated': 'ยังมีเงื่อนไขการประมวลผล',
        'report.validation': 'สรุปการตรวจสอบ',
        'report.brief': 'สรุปการปฏิบัติ',
        'report.detailed': 'รายละเอียด',
        'dataset.fixture': 'ข้อมูลตัวอย่าง',
        'dataset.mae': 'แม่สาย: ข้อมูลอ้างอิงแบบอ่อน',
        'dataset.blocker': 'ข้อมูลเมทาดาทาและข้อจำกัด',
        'scenario.baseline': 'สถานการณ์ฐาน',
        'scenario.shelter': 'ผลต่างเมื่อเพิ่มศูนย์พักพิงชั่วคราว',
        'scenario.road': 'ผลต่างเมื่อปิดถนน',
        'map.regional': 'ภาพรวม: ถนนสำคัญและกลุ่มสถานที่',
        'map.detail': 'รายละเอียดพื้นที่ที่เลือก',
        'map.fixtureDetail': 'รายละเอียดแผนที่ตัวอย่าง',
        'map.reportingOnly': 'ขอบเขตรายงานเท่านั้น',
        'map.roadSegments': 'ช่วงถนน',
        'map.priorityRoads': 'ถนนที่ควรให้ความสำคัญ',
        'map.selectedRoads': 'ถนนในพื้นที่ที่เลือก',
        'map.facilityClusters': 'กลุ่มสถานที่',
        'map.facilities': 'สถานที่',
        'common.unavailable': 'ไม่มีข้อมูล',
        'common.withheld': 'ไม่แสดง',
        'common.gated': 'ยังไม่อนุญาต',
        'common.of': 'จาก'
      }
    };
    const actionColors = {
      A: '#c13f3f', B: '#cf6a32', C: '#d39d20', D: '#167a55', E: '#6956a3'
    };
    const actionLabels = {
      en: { A: 'Protect Lives Now', B: 'Keep Routes Open', C: 'Protect Essential Services', D: 'Build Resilience', E: 'Monitor and Verify' },
      th: { A: 'คุ้มครองชีวิตทันที', B: 'รักษาเส้นทางให้ใช้งานได้', C: 'คุ้มครองบริการสำคัญ', D: 'เสริมความยืดหยุ่น', E: 'ติดตามและตรวจสอบ' }
    };
    const deltaColors = {
      improvement: '#167a55', worsening: '#c13f3f', neutral: '#7b8982'
    };
    const datasetModeNotes = {
      fixture_demo: 'Fixture demo: synthetic priority, access, equity, and road-risk outputs. Use this mode to judge the decision workflow, not real flood accuracy.',
      mae_sai_weak_reference: '__MAE_SAI_WEAK_NOTE__',
      metadata_blocker_view: 'Metadata/blocker view: source inventory and file readiness are visible, while decision values and operational interpretation remain gated.'
    };
    const datasetRegistry = {
      fixture_demo: {
        label: 'Fixture demo',
        priority: priorityData,
        roads: roadRiskData,
        facilities: emptyFeatureCollection,
        hotspots: emptyFeatureCollection,
        briefs: briefsBySubdistrict,
        supportsScenarios: true,
        metadataOnly: false
      },
      mae_sai_weak_reference: {
        label: 'Mae Sai weak-reference candidate',
        priority: maeSaiPriorityData,
        roads: maeSaiRoadRiskData,
        facilities: maeSaiFacilityData,
        hotspots: maeSaiAccessHotspotData,
        briefs: maeSaiBriefsBySubdistrict,
        supportsScenarios: false,
        metadataOnly: false
      },
      metadata_blocker_view: {
        label: 'Metadata/blocker view',
        priority: maeSaiPriorityData,
        roads: emptyFeatureCollection,
        facilities: emptyFeatureCollection,
        hotspots: emptyFeatureCollection,
        briefs: {},
        supportsScenarios: false,
        metadataOnly: true
      }
    };
    const mapBoundsPadding = 0.12;
    const semanticDetailZoom = 12;
    const state = {
      selectedId: '__TOP_ID__',
      scenario: 'baseline',
      datasetMode: 'fixture_demo',
      visibleClasses: new Set(['A', 'B', 'C', 'D', 'E']),
      showPriority: true,
      showRoads: true,
      showFacilities: true,
      showHotspots: true,
      focusSelected: true,
      language: 'en',
      judgeMode: false
    };
    let featuresById = new Map();
    const featureLayers = new Map();

    const map = L.map('map', { scrollWheelZoom: false, preferCanvas: true });
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);

    const priorityLayer = L.geoJSON(null, {
      style: priorityStyle,
      onEachFeature: bindPriorityFeature
    });
    const roadLayer = L.geoJSON(null, {
      style: roadStyle,
      onEachFeature: (feature, layer) => layer.bindPopup(roadPopup(feature.properties))
    });
    const facilityLayer = L.layerGroup();
    const accessHotspotLayer = L.geoJSON(null, {
      pointToLayer: accessHotspotPoint,
      onEachFeature: (feature, layer) => layer.bindPopup(accessHotspotPopup(feature.properties))
    });

    function activeDataset() {
      return datasetRegistry[state.datasetMode] || datasetRegistry.fixture_demo;
    }

    function tr(key) {
      return translations[state.language]?.[key] || translations.en[key] || key;
    }

    function localizedSubdistrictName(props) {
      if (state.language === 'th' && props.subdistrict_name_th) return String(props.subdistrict_name_th);
      return String(props.subdistrict_name || tr('common.unavailable'));
    }

    function datasetLabel(mode = state.datasetMode) {
      if (mode === 'mae_sai_weak_reference') return tr('dataset.mae');
      if (mode === 'metadata_blocker_view') return tr('dataset.blocker');
      return tr('dataset.fixture');
    }

    function datasetModeNote() {
      if (state.language === 'th') {
        if (state.datasetMode === 'mae_sai_weak_reference') return 'โหมดแม่สายใช้ Sentinel-1 และข้อมูลเปิดจริงร่วมกับข้อมูลอ้างอิงแบบอ่อน ผลลัพธ์เป็นเพียงข้อมูลประกอบการวางแผนและไม่ใช่การตรวจสอบอย่างเป็นทางการ';
        if (state.datasetMode === 'metadata_blocker_view') return 'โหมดนี้แสดงเมทาดาทาและความพร้อมของไฟล์เท่านั้น โดยซ่อนค่าการตัดสินใจและการตีความเชิงปฏิบัติการ';
        return 'โหมดข้อมูลตัวอย่างใช้ข้อมูลสังเคราะห์เพื่อสาธิตการจัดลำดับความสำคัญ การเข้าถึง ความเสมอภาค และความเสี่ยงถนน';
      }
      return datasetModeNotes[state.datasetMode] || datasetModeNotes.fixture_demo;
    }

    function applyStaticTranslations() {
      document.documentElement.lang = state.language;
      document.title = tr('app.title');
      document.querySelectorAll('[data-i18n]').forEach((element) => {
        const key = element.dataset.i18n;
        if (translations[state.language]?.[key] || translations.en[key]) element.textContent = tr(key);
      });
      document.getElementById('language-en').setAttribute('aria-pressed', String(state.language === 'en'));
      document.getElementById('language-th').setAttribute('aria-pressed', String(state.language === 'th'));
      document.getElementById('judge-mode-toggle').textContent = tr(state.judgeMode ? 'judge.exit' : 'judge.enter');
      setText('controls-title', tr(state.judgeMode ? 'controls.presentationTitle' : 'controls.title'));
      setText('controls-subtitle', tr(state.judgeMode ? 'controls.presentationSubtitle' : 'controls.subtitle'));
      const datasetSelect = document.getElementById('dataset-mode-select');
      datasetSelect.options[0].textContent = tr('dataset.fixture');
      datasetSelect.options[1].textContent = tr('dataset.mae');
      datasetSelect.options[2].textContent = tr('dataset.blocker');
      const scenarioSelect = document.getElementById('scenario-select');
      scenarioSelect.options[0].textContent = tr('scenario.baseline');
      scenarioSelect.options[1].textContent = tr('scenario.shelter');
      scenarioSelect.options[2].textContent = tr('scenario.road');
    }

    function setLanguage(language) {
      state.language = language === 'th' ? 'th' : 'en';
      applyStaticTranslations();
      populateSubdistrictSelector();
      renderAllMapLayers();
      updateModeChrome();
      updateSelectedPanel();
    }

    function setJudgeMode(enabled) {
      state.judgeMode = Boolean(enabled);
      document.body.classList.toggle('judge-mode', state.judgeMode);
      const button = document.getElementById('judge-mode-toggle');
      button.setAttribute('aria-pressed', String(state.judgeMode));
      button.textContent = tr(state.judgeMode ? 'judge.exit' : 'judge.enter');
      setText('controls-title', tr(state.judgeMode ? 'controls.presentationTitle' : 'controls.title'));
      setText('controls-subtitle', tr(state.judgeMode ? 'controls.presentationSubtitle' : 'controls.subtitle'));
      document.getElementById('sar-evidence-drawer').open = state.judgeMode;
      document.getElementById('technical-provenance').open = false;
      if (state.judgeMode) map.closePopup();
      window.setTimeout(() => {
        map.invalidateSize({ pan: false });
      }, 80);
    }

    function initializeDashboardControls() {
      document.getElementById('subdistrict-select').addEventListener('change', (event) => {
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
        applyDatasetMode();
      });
      document.getElementById('toggle-focus').addEventListener('change', (event) => {
        state.focusSelected = event.target.checked;
        renderPriorityLayer();
      });
      document.getElementById('language-en').addEventListener('click', () => setLanguage('en'));
      document.getElementById('language-th').addEventListener('click', () => setLanguage('th'));
      document.getElementById('judge-mode-toggle').addEventListener('click', () => setJudgeMode(!state.judgeMode));
      document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && state.judgeMode) setJudgeMode(false);
      });
      bindLayerToggle('toggle-priority', 'showPriority', priorityLayer);
      bindLayerToggle('toggle-roads', 'showRoads', roadLayer);
      bindLayerToggle('toggle-facilities', 'showFacilities', facilityLayer);
      bindLayerToggle('toggle-hotspots', 'showHotspots', accessHotspotLayer);
      document.getElementById('download-current-brief').addEventListener('click', downloadCurrentActionBrief);
      document.getElementById('download-filtered-geojson').addEventListener('click', downloadFilteredGeoJSON);
      map.on('zoomend', renderSemanticContextLayers);
      applyStaticTranslations();
      applyDatasetMode(true);
    }

    function bindLayerToggle(elementId, stateKey, layer) {
      document.getElementById(elementId).addEventListener('change', (event) => {
        state[stateKey] = event.target.checked;
        syncLayerVisibility(layer, state[stateKey]);
      });
    }

    function applyDatasetMode(initial = false) {
      const dataset = activeDataset();
      state.scenario = 'baseline';
      state.visibleClasses = new Set(['A', 'B', 'C', 'D', 'E']);
      document.querySelectorAll('.action-filter').forEach((input) => {
        input.checked = true;
        input.disabled = dataset.metadataOnly;
      });
      const scenarioSelect = document.getElementById('scenario-select');
      scenarioSelect.value = 'baseline';
      scenarioSelect.disabled = !dataset.supportsScenarios;
      state.selectedId = selectDefaultId(dataset.priority, state.datasetMode === 'fixture_demo');
      rebuildFeatureIndex();
      populateSubdistrictSelector();
      renderAllMapLayers();
      updateModeChrome();
      updateSelectedPanel();
      if (!initial) {
        requestAnimationFrame(settleMapLayout);
      }
    }

    function selectDefaultId(collection, actionableFirst) {
      const features = collection.features || [];
      if (!features.length) {
        return '';
      }
      const order = { A: 0, B: 1, C: 2, D: 3, E: 4 };
      const sorted = features.slice().sort((left, right) => {
        const leftProps = left.properties || {};
        const rightProps = right.properties || {};
        if (actionableFirst) {
          const classDifference = (order[leftProps.action_class] ?? 9) - (order[rightProps.action_class] ?? 9);
          if (classDifference !== 0) {
            return classDifference;
          }
        }
        return numeric(rightProps.fpps_0_100, -Infinity) - numeric(leftProps.fpps_0_100, -Infinity);
      });
      return String(sorted[0].properties.subdistrict_id || '');
    }

    function rebuildFeatureIndex() {
      featuresById = new Map(
        (activeDataset().priority.features || []).map((feature) => [
          String(feature.properties.subdistrict_id), feature
        ])
      );
    }

    function populateSubdistrictSelector() {
      const selector = document.getElementById('subdistrict-select');
      selector.replaceChildren();
      [...featuresById.values()]
        .sort((left, right) => String(left.properties.subdistrict_id).localeCompare(String(right.properties.subdistrict_id)))
        .forEach((feature) => {
          const props = feature.properties;
          const option = document.createElement('option');
          option.value = String(props.subdistrict_id);
          option.textContent = `${props.subdistrict_id} / ${localizedSubdistrictName(props)}`;
          selector.appendChild(option);
        });
      selector.value = state.selectedId;
      selector.disabled = selector.options.length === 0;
    }

    function renderAllMapLayers() {
      renderPriorityLayer();
      const dataset = activeDataset();
      renderRoadLayer();
      renderFacilityLayer();
      accessHotspotLayer.clearLayers();
      accessHotspotLayer.addData({
        type: 'FeatureCollection',
        features: (dataset.hotspots.features || []).filter((feature) =>
          numeric(feature.properties.people_losing_30_min_access, 0) > 0
        )
      });
      syncLayerVisibility(priorityLayer, state.showPriority);
      syncLayerVisibility(roadLayer, state.showRoads && roadLayer.getLayers().length > 0);
      syncLayerVisibility(facilityLayer, state.showFacilities && facilityLayer.getLayers().length > 0);
      syncLayerVisibility(accessHotspotLayer, state.showHotspots && accessHotspotLayer.getLayers().length > 0);
      updateLayerToggleAvailability();
      updateMapDetailStatus();
    }

    function isSelectedAreaDetail() {
      return state.datasetMode === 'mae_sai_weak_reference' && map.getZoom() >= semanticDetailZoom;
    }

    function visibleRoadFeatures() {
      const features = activeDataset().roads.features || [];
      if (state.datasetMode !== 'mae_sai_weak_reference') return features;
      if (isSelectedAreaDetail()) {
        return features.filter((feature) => String(feature.properties.subdistrict_id) === state.selectedId);
      }
      return features.filter((feature) => {
        const props = feature.properties || {};
        const status = String(props.candidate_status || 'candidate_open_with_delay');
        return status === 'candidate_closed' || status === 'candidate_delayed' || numeric(props.road_disruption_probability_0_1, 0) >= .2;
      });
    }

    function renderRoadLayer() {
      const features = visibleRoadFeatures();
      roadLayer.clearLayers();
      roadLayer.addData({ type: 'FeatureCollection', features });
      syncLayerVisibility(roadLayer, state.showRoads && features.length > 0);
    }

    function renderFacilityLayer() {
      const features = activeDataset().facilities.features || [];
      facilityLayer.clearLayers();
      if (!features.length) {
        syncLayerVisibility(facilityLayer, false);
        return;
      }
      if (isSelectedAreaDetail()) {
        features
          .filter((feature) => String(feature.properties.subdistrict_id) === state.selectedId)
          .forEach((feature) => facilityLayer.addLayer(facilityMarker(feature)));
      } else {
        const clusters = new Map();
        features.forEach((feature) => {
          const props = feature.properties || {};
          const id = String(props.subdistrict_id || 'unassigned');
          const coordinates = feature.geometry?.coordinates || [];
          if (coordinates.length < 2) return;
          const cluster = clusters.get(id) || { id, lat: 0, lon: 0, features: [], types: {} };
          cluster.lon += numeric(coordinates[0], 0);
          cluster.lat += numeric(coordinates[1], 0);
          cluster.features.push(feature);
          const type = normalizedFacilityType(props.facility_type, props.amenity);
          cluster.types[type] = (cluster.types[type] || 0) + 1;
          clusters.set(id, cluster);
        });
        clusters.forEach((cluster) => facilityLayer.addLayer(facilityClusterMarker(cluster)));
      }
      syncLayerVisibility(facilityLayer, state.showFacilities && facilityLayer.getLayers().length > 0);
    }

    function facilityMarker(feature) {
      const props = feature.properties || {};
      const coordinates = feature.geometry?.coordinates || [0, 0];
      const type = normalizedFacilityType(props.facility_type, props.amenity);
      const icon = L.divIcon({
        className: 'facility-marker-shell',
        html: `<span class="facility-symbol ${escapeHtml(type)}" aria-hidden="true"></span>`,
        iconSize: [24, 24],
        iconAnchor: [12, 12],
        popupAnchor: [0, -12]
      });
      return L.marker([coordinates[1], coordinates[0]], { icon }).bindPopup(facilityPopup(props));
    }

    function facilityClusterMarker(cluster) {
      const count = cluster.features.length;
      const marker = L.marker([cluster.lat / count, cluster.lon / count], {
        icon: L.divIcon({
          className: 'facility-cluster-shell',
          html: `<span class="facility-cluster" aria-label="${escapeHtml(`${count} ${tr('map.facilities')}`)}">${count}</span>`,
          iconSize: [30, 30],
          iconAnchor: [15, 15],
          popupAnchor: [0, -15]
        })
      });
      const breakdown = Object.entries(cluster.types)
        .sort((left, right) => right[1] - left[1])
        .map(([type, value]) => `${escapeHtml(facilityTypeLabel(type))}: ${value}`)
        .join('<br>');
      const selected = featuresById.get(cluster.id)?.properties || {};
      marker.bindPopup(`<strong>${escapeHtml(cluster.id)} / ${escapeHtml(localizedSubdistrictName(selected))}</strong><br>${breakdown}<br><small>${escapeHtml(state.language === 'th' ? 'กลุ่มสถานที่จาก OSM ที่ยังไม่ได้ตรวจสอบภาคสนาม' : 'Clustered OSM candidates; not field verified.')}</small>`);
      return marker;
    }

    function normalizedFacilityType(value, amenity = '') {
      const type = String(value || 'community_facility');
      const normalizedAmenity = String(amenity || '').toLowerCase();
      if (type === 'healthcare' && normalizedAmenity === 'hospital') return 'hospital';
      if (type === 'healthcare' && normalizedAmenity === 'clinic') return 'clinic';
      return ['hospital', 'clinic', 'healthcare', 'school', 'shelter_candidate', 'emergency_service', 'community_facility'].includes(type) ? type : 'community_facility';
    }

    function facilityTypeLabel(value) {
      const type = normalizedFacilityType(value);
      const labels = state.language === 'th'
        ? { hospital: 'โรงพยาบาล', clinic: 'คลินิก', healthcare: 'สาธารณสุข', school: 'โรงเรียน', shelter_candidate: 'ที่พักพิง', emergency_service: 'บริการฉุกเฉิน', community_facility: 'สถานที่ชุมชน' }
        : { hospital: 'Hospital', clinic: 'Clinic', healthcare: 'Healthcare', school: 'School', shelter_candidate: 'Shelter', emergency_service: 'Emergency service', community_facility: 'Community facility' };
      return labels[type];
    }

    function confidenceLabel(value) {
      const key = String(value || 'unavailable').toLowerCase();
      if (state.language !== 'th') return key;
      return { high: 'สูง', medium: 'ปานกลาง', low: 'ต่ำ', unavailable: 'ไม่มีข้อมูล' }[key] || key;
    }

    function localizedDecisionReason(props) {
      if (state.language !== 'th') return props.top_reason || 'No reason recorded.';
      const action = actionLabels.th[props.action_class] || 'ติดตามและตรวจสอบ';
      return `${action} โดยใช้หลักฐานผู้สมัครและตรวจสอบกับข้อมูลภาคสนามก่อนตัดสินใจ`;
    }

    function renderSemanticContextLayers() {
      renderRoadLayer();
      renderFacilityLayer();
      updateMapDetailStatus();
    }

    function updateMapDetailStatus() {
      const roadCount = visibleRoadFeatures().length;
      if (state.datasetMode === 'fixture_demo') {
        setText('map-detail-status', `${tr('map.fixtureDetail')} | ${roadCount} ${tr('map.roadSegments')}`);
        return;
      }
      if (state.datasetMode === 'metadata_blocker_view') {
        setText('map-detail-status', tr('map.reportingOnly'));
        return;
      }
      const detail = isSelectedAreaDetail();
      const facilityCount = facilityLayer.getLayers().length;
      const label = detail ? tr('map.detail') : tr('map.regional');
      const roadLabel = detail ? tr('map.selectedRoads') : tr('map.priorityRoads');
      const facilityLabel = detail ? tr('map.facilities') : tr('map.facilityClusters');
      setText('map-detail-status', `${label} | ${roadCount} ${roadLabel} | ${facilityCount} ${facilityLabel}`);
    }

    function renderPriorityLayer() {
      featureLayers.clear();
      priorityLayer.clearLayers();
      const visibleFeatures = (activeDataset().priority.features || []).filter((feature) =>
        state.visibleClasses.has(String(feature.properties.action_class))
      );
      priorityLayer.addData({ type: 'FeatureCollection', features: visibleFeatures });
      syncLayerVisibility(priorityLayer, state.showPriority);
    }

    function syncLayerVisibility(layer, shouldShow) {
      if (shouldShow && !map.hasLayer(layer)) {
        layer.addTo(map);
      } else if (!shouldShow && map.hasLayer(layer)) {
        layer.removeFrom(map);
      }
    }

    function updateLayerToggleAvailability() {
      const dataset = activeDataset();
      setToggleAvailability('toggle-roads', (dataset.roads.features || []).length > 0);
      setToggleAvailability('toggle-facilities', (dataset.facilities.features || []).length > 0);
      setToggleAvailability(
        'toggle-hotspots',
        (dataset.hotspots.features || []).some((feature) =>
          numeric(feature.properties.people_losing_30_min_access, 0) > 0
        )
      );
    }

    function setToggleAvailability(elementId, available) {
      const input = document.getElementById(elementId);
      input.disabled = !available;
      input.closest('label').style.opacity = available ? '1' : '.45';
    }

    function bindPriorityFeature(feature, layer) {
      const id = String(feature.properties.subdistrict_id);
      const name = localizedSubdistrictName(feature.properties);
      const labelOffsets = {
        TH570901: [0, -11],
        TH570906: [0, 11]
      };
      featureLayers.set(id, layer);
      layer.bindPopup(priorityPopup(feature.properties));
      layer.bindTooltip(
        `<strong>${escapeHtml(id)}</strong><span>${escapeHtml(name)}</span>`,
        {
          permanent: true,
          direction: 'center',
          className: 'subdistrict-label',
          offset: labelOffsets[id] || [0, 0]
        }
      );
      layer.on('click', () => selectSubdistrict(id, false));
    }

    function fitPriorityMapToData() {
      map.invalidateSize({ pan: false });
      const bounds = priorityLayer.getBounds();
      if (bounds.isValid()) {
        map.fitBounds(bounds.pad(mapBoundsPadding), { animate: false });
      } else {
        map.setView([20.43, 99.88], 11);
      }
    }

    function settleMapLayout() {
      fitPriorityMapToData();
      window.setTimeout(fitPriorityMapToData, 80);
      window.setTimeout(fitPriorityMapToData, 350);
    }

    function preserveMapViewAfterLayout() {
      map.invalidateSize({ pan: false });
      window.setTimeout(() => map.invalidateSize({ pan: false }), 80);
    }

    function selectSubdistrict(subdistrictId, zoomToFeature) {
      state.selectedId = String(subdistrictId);
      document.getElementById('subdistrict-select').value = state.selectedId;
      updateSelectedPanel();
      renderPriorityLayer();
      renderSemanticContextLayers();
      if (zoomToFeature) {
        zoomToSelectedFeature();
      }
    }

    function updateSelectedPanel() {
      const feature = featuresById.get(state.selectedId);
      if (!feature) {
        return;
      }
      const dataset = activeDataset();
      const props = feature.properties;
      const metrics = normalizedMetrics(props);
      const metadataOnly = dataset.metadataOnly;
      setText('panel-subdistrict', props.subdistrict_id);
      setText('panel-subdistrict-name', localizedSubdistrictName(props));
      setText('panel-class', metadataOnly ? '-' : (props.action_class || tr('common.unavailable')));
      setText('panel-action-label', metadataOnly ? tr('common.gated') : (actionLabels[state.language]?.[props.action_class] || tr('common.unavailable')));
      setText('panel-fpps', metadataOnly ? tr('common.gated') : formatNumber(props.fpps_0_100, 2));
      setText('panel-confidence', confidenceLabel(props.confidence_class));
      setText('panel-confidence-note', state.datasetMode === 'fixture_demo' ? (state.language === 'th' ? 'ระดับจากข้อมูลตัวอย่าง' : 'fixture class') : (state.language === 'th' ? 'ความเชื่อมั่นของข้อมูลผู้สมัคร' : 'candidate confidence'));
      setText('panel-baseline-access', metadataOnly ? tr('common.gated') : formatCompact(metrics.accessLoss));
      setText('panel-baseline-equity', metadataOnly ? tr('common.gated') : formatNumber(metrics.equityGap, 3));
      setText('panel-detail-title', `${props.subdistrict_id} / ${localizedSubdistrictName(props)}`);
      setText('panel-detail-class', metadataOnly ? (state.language === 'th' ? 'เมทาดาทาเท่านั้น' : 'Metadata only') : `${state.language === 'th' ? 'ระดับ' : 'Class'} ${props.action_class || tr('common.unavailable')}`);
      setText('panel-detail-access', metadataOnly ? tr('common.withheld') : formatCompact(metrics.accessLoss));
      setText('panel-detail-equity', metadataOnly ? tr('common.withheld') : formatNumber(metrics.equityGap, 3));
      setText('panel-reason', metadataOnly ? (state.language === 'th' ? 'ซ่อนผลการตัดสินใจในโหมดข้อจำกัด' : 'Decision outputs are intentionally withheld in blocker view.') : localizedDecisionReason(props));
      updateKpiMode(props, metrics, metadataOnly);
      updateEvidencePanel(props, metrics, metadataOnly);
      updateModelContextPanel(props, metadataOnly);
      updateComparison(props, metadataOnly);
      updateQualityPanel(props);
      updateSarEvidencePanel(props, metadataOnly);
      updateProvenancePanel(props);
      updateReportPanel(props, metrics, metadataOnly);
      setText('dataset-mode-note', datasetModeNote());
      const brief = currentBriefContent(props);
      setText('action-brief-pre', brief);
      document.getElementById('download-current-brief').disabled = metadataOnly;
      document.getElementById('download-filtered-geojson').disabled = metadataOnly;
      updateClassPill(props.action_class, metadataOnly);
    }

    function normalizedMetrics(props) {
      const fixture = state.datasetMode === 'fixture_demo';
      return {
        accessLoss: fixture ? props.baseline_people_losing_30_min_access : props.people_losing_30_min_access,
        equityGap: fixture ? props.baseline_equity_gap_ratio : props.equity_gap_ratio,
        floodLikelihood: props.flood_likelihood_0_100,
        exposure: fixture ? props.exposure_0_100 : props.expected_exposed_population_proxy,
        roadCriticality: props.road_criticality_0_100,
        terrain: props.mean_slope_degrees,
        demCoverage: props.dem_population_coverage_rate
      };
    }

    function updateKpiMode(props, metrics, metadataOnly) {
      const fixture = state.datasetMode === 'fixture_demo';
      setText('panel-access-note', fixture ? (state.language === 'th' ? 'ประชากรในสถานการณ์ฐาน' : 'baseline people') : (state.language === 'th' ? 'ประชากรจากแบบจำลองผู้สมัคร' : 'modeled candidate people'));
      setText('panel-kpi-seven-label', fixture ? (state.language === 'th' ? 'สถานการณ์ศูนย์พักพิง' : 'Shelter scenario') : (state.language === 'th' ? 'ความน่าจะเป็นน้ำท่วม' : 'Flood likelihood'));
      setText('panel-kpi-seven-note', fixture ? (state.language === 'th' ? 'การเปลี่ยนแปลงการเข้าถึง 30 นาที' : '30-min access change') : (state.language === 'th' ? 'ความน่าจะเป็นเฉลี่ยของข้อมูลผู้สมัคร' : 'mean candidate probability'));
      setText('panel-kpi-eight-label', fixture ? (state.language === 'th' ? 'การปิดถนน' : 'Road closure') : (state.language === 'th' ? 'ประชากรที่อาจได้รับผลกระทบ' : 'Expected exposure'));
      setText('panel-kpi-eight-note', fixture ? (state.language === 'th' ? 'การเปลี่ยนแปลงในกรณีทดสอบ' : 'stress-case change') : (state.language === 'th' ? 'ค่าประมาณจาก WorldPop และความน่าจะเป็น' : 'WorldPop probability proxy'));
      if (metadataOnly) {
        setKpiValue('panel-temp-delta', tr('common.gated'));
        setKpiValue('panel-road-delta', tr('common.gated'));
      } else if (fixture) {
        setDeltaBadge('panel-temp-delta', props.temporary_shelter_change_people_losing_30_min_access);
        setDeltaBadge('panel-road-delta', props.road_closure_change_people_losing_30_min_access);
      } else {
        setKpiValue('panel-temp-delta', `${formatNumber(metrics.floodLikelihood, 1)}%`);
        setKpiValue('panel-road-delta', formatCompact(metrics.exposure));
      }
    }

    function setKpiValue(elementId, value) {
      const element = document.getElementById(elementId);
      element.textContent = value;
      element.classList.remove('good', 'bad');
    }

    function updateEvidencePanel(props, metrics, metadataOnly) {
      if (metadataOnly) {
        ['panel-evidence-flood', 'panel-evidence-exposure', 'panel-evidence-roads', 'panel-evidence-terrain'].forEach((id) => setText(id, tr('common.withheld')));
        const gateNote = state.language === 'th' ? 'แสดงเฉพาะเมทาดาทาและเงื่อนไข' : 'metadata and gates only';
        setText('panel-evidence-flood-note', gateNote);
        setText('panel-evidence-exposure-note', gateNote);
        setText('panel-evidence-access-note', gateNote);
        setText('panel-evidence-equity-note', gateNote);
        setText('panel-evidence-roads-note', gateNote);
        setText('panel-evidence-terrain-note', gateNote);
        return;
      }
      const fixture = state.datasetMode === 'fixture_demo';
      setText('panel-evidence-flood', `${formatNumber(metrics.floodLikelihood, 1)}%`);
      setText('panel-evidence-flood-note', fixture ? (state.language === 'th' ? 'คะแนนความน่าจะเป็นสังเคราะห์' : 'synthetic likelihood score') : `P90 ${formatPercent(props.p90_flood_probability_0_1)}`);
      setText('panel-evidence-exposure', fixture ? `${formatNumber(metrics.exposure, 1)} / 100` : `${formatCompact(metrics.exposure)} people`);
      setText('panel-evidence-exposure-note', fixture ? (state.language === 'th' ? 'คะแนนการรับสัมผัสสังเคราะห์' : 'synthetic exposure score') : (state.language === 'th' ? 'ค่าประมาณจาก WorldPop และความน่าจะเป็น' : 'WorldPop probability proxy'));
      setText('panel-evidence-access-note', fixture ? (state.language === 'th' ? 'ประชากรสังเคราะห์ในสถานการณ์ฐาน' : 'synthetic baseline people') : (state.language === 'th' ? 'การกำหนดเส้นทางที่ถูกรบกวนโดยแบบจำลอง' : 'heuristic disrupted routing'));
      setText('panel-evidence-equity-note', fixture ? (state.language === 'th' ? 'อัตราส่วนกลุ่มเปราะบางในข้อมูลตัวอย่าง' : 'fixture vulnerable/non-vulnerable ratio') : (state.language === 'th' ? 'อัตราส่วนจากภูมิประเทศและความห่างไกล' : 'terrain/remoteness proxy ratio'));
      setText('panel-evidence-roads', `${formatNumber(metrics.roadCriticality, 1)} / 100`);
      setText('panel-evidence-roads-note', fixture ? (state.language === 'th' ? 'ความสำคัญของถนนในข้อมูลตัวอย่าง' : 'fixture road criticality') : `${formatCompact(props.road_count)} ${state.language === 'th' ? 'เส้นทางผู้สมัคร' : 'candidate ways'}`);
      setText('panel-evidence-terrain', fixture ? (state.language === 'th' ? 'บริบทตัวอย่าง' : 'Fixture context') : `${formatNumber(metrics.terrain, 1)}° ${state.language === 'th' ? 'ความชันเฉลี่ย' : 'mean slope'}`);
      setText('panel-evidence-terrain-note', fixture ? (state.language === 'th' ? 'ไม่ใช่หลักฐานภูมิประเทศจริง' : 'not real terrain evidence') : `${formatPercent(metrics.demCoverage)} ${state.language === 'th' ? 'ความครอบคลุม DEM' : 'DEM coverage'}`);
    }

    function updateModelContextPanel(props, metadataOnly) {
      const historicalCard = document.getElementById('historical-context-card');
      historicalCard.classList.remove('conflict');
      if (metadataOnly) {
        setText('panel-modality-used', tr('common.gated'));
        setText('panel-modality-reason', tr('model.decisionWithheld'));
        setText('panel-modality-meta', tr('model.gatesOnly'));
        setText('panel-historical-susceptibility', tr('common.gated'));
        setText('panel-historical-explanation', tr('model.historicalWithheld'));
        setText('panel-historical-warning', tr('model.noComparisonView'));
        setText('panel-historical-meta', tr('model.gatesOnly'));
        return;
      }

      const fixture = state.datasetMode === 'fixture_demo';
      const hasDeclaredSarEvidence = (
        Number.isFinite(numeric(props.mean_flood_probability_0_1, NaN))
        && String(props.source_name || '').includes('Sentinel-1')
      );
      const modality = props.fusion_candidate_mode || props.decision_input_mode || (hasDeclaredSarEvidence ? 'SAR only' : 'unavailable');
      const fallbackReason = props.fusion_fallback_reason || (
        hasDeclaredSarEvidence
          ? tr('model.existingSar')
          : fixture
          ? tr('model.noFusion')
          : tr('model.noMode')
      );
      const modalityTimestamp = props.fusion_source_timestamp || props.source_timestamp || tr('common.unavailable');
      const modalityConfidence = props.fusion_confidence_class || props.confidence_class || tr('common.unavailable');
      setText('panel-modality-used', modality);
      setText('panel-modality-reason', fallbackReason);
      setText('panel-modality-meta', `${tr('model.sourceTime')}: ${modalityTimestamp} | ${tr('model.confidence')}: ${modalityConfidence}`);

      const susceptibility = numeric(props.historical_susceptibility_0_100, NaN);
      const susceptibilityClass = props.historical_susceptibility_class || 'unavailable';
      const explanation = props.historical_explanation || tr('model.noHistorical');
      const conflictStatus = props.historical_conflict_status || 'unavailable';
      const conflictWarning = props.historical_conflict_warning || tr('model.noComparison');
      const historicalTimestamp = props.historical_source_timestamp || tr('common.unavailable');
      const historicalConfidence = props.historical_confidence_class || tr('common.unavailable');
      const calibrationStatus = props.calibration_status || tr('common.unavailable');
      setText(
        'panel-historical-susceptibility',
        Number.isFinite(susceptibility)
          ? `${formatNumber(susceptibility, 1)} / 100 · ${susceptibilityClass}`
          : tr('common.unavailable')
      );
      setText('panel-historical-explanation', explanation);
      setText('panel-historical-warning', conflictWarning);
      setText(
        'panel-historical-meta',
        `${tr('model.sourceTime')}: ${historicalTimestamp} | ${tr('model.confidence')}: ${historicalConfidence} | ${tr('model.calibration')}: ${calibrationStatus}`
      );
      historicalCard.classList.toggle(
        'conflict',
        !['none', 'unavailable', 'not_evaluated'].includes(String(conflictStatus))
      );
    }

    function updateComparison(props, metadataOnly) {
      if (metadataOnly) {
        setText('comparison-rank', tr('common.withheld'));
        setText('comparison-flood', tr('common.withheld'));
        setText('comparison-access', tr('common.withheld'));
        return;
      }
      const features = activeDataset().priority.features || [];
      const sorted = features.slice().sort((left, right) => numeric(right.properties.fpps_0_100, -Infinity) - numeric(left.properties.fpps_0_100, -Infinity));
      const rank = sorted.findIndex((feature) => String(feature.properties.subdistrict_id) === state.selectedId) + 1;
      const floodValues = features.map((feature) => numeric(feature.properties.flood_likelihood_0_100, NaN)).filter(Number.isFinite).sort((a, b) => a - b);
      const selectedFlood = numeric(props.flood_likelihood_0_100, NaN);
      const accessValues = features.map((feature) => numeric(normalizedMetrics(feature.properties).accessLoss, 0));
      const maxAccess = accessValues.length ? Math.max(...accessValues) : 0;
      setText('comparison-rank', `${rank} ${tr('common.of')} ${features.length}`);
      setText('comparison-flood', `${formatNumber(selectedFlood, 1)} ${state.language === 'th' ? 'เทียบ' : 'vs'} ${formatNumber(median(floodValues), 1)}%`);
      setText('comparison-access', `${formatCompact(normalizedMetrics(props).accessLoss)} ${tr('common.of')} ${formatCompact(maxAccess)}`);
    }

    function updateQualityPanel(props) {
      const fixture = state.datasetMode === 'fixture_demo';
      if (fixture) {
        setQualityRow('quality-population', 1, 'synthetic');
        setQualityRow('quality-road', 1, 'synthetic');
        setQualityRow('quality-dem', 1, 'synthetic');
        setQualityRow('quality-reference', 1, 'fixture');
        setText('quality-confidence', 'fixture completeness');
        return;
      }
      setQualityRow('quality-population', numeric(props.worldpop_bbox_coverage_rate, numeric(maeSaiContextQuality.minimum_worldpop_bbox_coverage_rate, 0)), formatPercent(props.worldpop_bbox_coverage_rate));
      setQualityRow('quality-road', numeric(props.road_snap_population_coverage_rate, numeric(maeSaiContextQuality.minimum_road_snap_population_coverage_rate, 0)), formatPercent(props.road_snap_population_coverage_rate));
      setQualityRow('quality-dem', numeric(props.dem_population_coverage_rate, numeric(maeSaiContextQuality.minimum_dem_population_coverage_rate, 0)), formatPercent(props.dem_population_coverage_rate));
      setQualityRow('quality-reference', 0, state.language === 'th' ? 'อ้างอิงข้ามพรมแดนเท่านั้น' : 'cross-border only');
      setText('quality-confidence', state.language === 'th' ? `ความเชื่อมั่น${confidenceLabel(props.confidence_class || 'low')}` : `${props.confidence_class || 'low'} confidence`);
    }

    function setQualityRow(prefix, ratio, label) {
      const bounded = Math.max(0, Math.min(1, numeric(ratio, 0)));
      const fill = document.getElementById(`${prefix}-fill`);
      fill.style.width = `${bounded * 100}%`;
      fill.classList.toggle('partial', bounded < .95);
      setText(`${prefix}-value`, label === 'unavailable' ? `${(bounded * 100).toFixed(0)}%` : label);
    }

    function updateSarEvidencePanel(props, metadataOnly) {
      const fixture = state.datasetMode === 'fixture_demo';
      const sar = maeSaiSarContext[String(props.subdistrict_id)] || {};
      const status = document.getElementById('sar-evidence-status');
      if (metadataOnly) {
        status.textContent = tr('common.gated');
        setText('sar-pre-date', tr('common.withheld'));
        setText('sar-post-date', tr('common.withheld'));
        setText('sar-pre-product', tr('common.withheld'));
        setText('sar-post-product', tr('common.withheld'));
        setText('sar-change-score', tr('common.withheld'));
        setSarBar('sar-mean', 0, tr('common.withheld'));
        setSarBar('sar-p90', 0, tr('common.withheld'));
        setSarBar('sar-binary', 0, tr('common.withheld'));
        return;
      }
      if (fixture) {
        status.textContent = state.language === 'th' ? 'ข้อมูลตัวอย่าง' : 'fixture';
        setText('sar-pre-date', state.language === 'th' ? 'ข้อมูลสังเคราะห์' : 'synthetic input');
        setText('sar-post-date', state.language === 'th' ? 'ข้อมูลสังเคราะห์' : 'synthetic input');
        setText('sar-pre-product', state.language === 'th' ? 'ไม่ใช่ผลิตภัณฑ์ดาวเทียม' : 'not a satellite product');
        setText('sar-post-product', state.language === 'th' ? 'ไม่ใช่ผลิตภัณฑ์ดาวเทียม' : 'not a satellite product');
        setText('sar-change-score', `${formatNumber(props.flood_likelihood_0_100, 1)}%`);
        setSarBar('sar-mean', numeric(props.flood_likelihood_0_100, 0) / 100, `${formatNumber(props.flood_likelihood_0_100, 1)}%`);
        setSarBar('sar-p90', 0, tr('common.unavailable'));
        setSarBar('sar-binary', 0, tr('common.unavailable'));
        return;
      }
      status.textContent = state.language === 'th' ? 'ข้อมูลอ้างอิงแบบอ่อน' : 'weak reference';
      setText('sar-pre-date', '2024-09-06');
      setText('sar-post-date', String(props.source_timestamp || '2024-09-15').slice(0, 10));
      setText('sar-pre-product', shortProductId(maeSaiWeakReferenceSummary.pre_product_id));
      setText('sar-post-product', shortProductId(maeSaiWeakReferenceSummary.post_product_id));
      setText('sar-change-score', `${formatSigned(sar.mean_combined_sar_change_score, 2)} dB`);
      setSarBar('sar-mean', numeric(props.mean_flood_probability_0_1, 0), formatPercent(props.mean_flood_probability_0_1));
      setSarBar('sar-p90', numeric(props.p90_flood_probability_0_1, 0), formatPercent(props.p90_flood_probability_0_1));
      setSarBar('sar-binary', numeric(props.binary_flood_share_0_1, 0), formatPercent(props.binary_flood_share_0_1));
    }

    function setSarBar(prefix, ratio, label) {
      const bounded = Math.max(0, Math.min(1, numeric(ratio, 0)));
      document.getElementById(`${prefix}-fill`).style.width = `${bounded * 100}%`;
      setText(`${prefix}-value`, label);
    }

    function shortProductId(value) {
      const text = String(value || tr('common.unavailable'));
      return text.length > 12 ? `${text.slice(0, 8)}...` : text;
    }

    function updateProvenancePanel(props) {
      const fixture = state.datasetMode === 'fixture_demo';
      setText('provenance-status', fixture ? (state.language === 'th' ? 'ข้อมูลตัวอย่าง' : 'fixture') : (state.datasetMode === 'metadata_blocker_view' ? tr('common.gated') : (state.language === 'th' ? 'ข้อมูลอ้างอิงแบบอ่อน' : 'weak reference')));
      setText('provenance-time', props.source_timestamp || tr('common.unavailable'));
      setText('provenance-pre', fixture ? (state.language === 'th' ? 'ข้อมูลสังเคราะห์' : 'synthetic fixture') : (maeSaiWeakReferenceSummary.pre_product_id || tr('common.unavailable')));
      setText('provenance-post', fixture ? (state.language === 'th' ? 'ข้อมูลสังเคราะห์' : 'synthetic fixture') : (maeSaiWeakReferenceSummary.post_product_id || tr('common.unavailable')));
      setText('provenance-reference', fixture ? (state.language === 'th' ? 'มาสก์สังเคราะห์' : 'synthetic fixture mask') : (props.reference_status || maeSaiWeakReferenceSummary.manual_reference_status || tr('common.unavailable')));
      setText('provenance-scope', props.processing_scope || (fixture ? 'fixture_demo' : 'candidate context'));
      setText('provenance-assumptions', props.assumptions || tr('common.unavailable'));
    }

    function updateReportPanel(props, metrics, metadataOnly) {
      const fixture = state.datasetMode === 'fixture_demo';
      const reportMetrics = fixture
        ? Object.fromEntries(fixtureValidationMetrics.map((item) => [
            String(item.label).toLowerCase().replace(' / ', '_').replace(' ', '_'),
            item.value
          ]))
        : metadataOnly
          ? { iou: 'gated', f1_dice: 'gated', precision: 'gated', recall: 'gated', area_error: 'gated' }
          : {
              iou: formatNumber(maeSaiWeakReferenceSummary.iou, 3),
              f1_dice: formatNumber(maeSaiWeakReferenceSummary.f1_dice, 3),
              precision: formatNumber(maeSaiWeakReferenceSummary.precision, 3),
              recall: formatNumber(maeSaiWeakReferenceSummary.recall, 3),
              area_error: formatRatioPercent(maeSaiWeakReferenceSummary.area_error_ratio)
            };
      const fixtureMetricFallback = {
        iou: fixtureValidationMetrics[0]?.value,
        f1_dice: fixtureValidationMetrics[1]?.value,
        precision: fixtureValidationMetrics[2]?.value,
        recall: fixtureValidationMetrics[3]?.value,
        area_error: fixtureValidationMetrics[4]?.value
      };
      for (const key of ['iou', 'f1_dice', 'precision', 'recall', 'area_error']) {
        const element = document.querySelector(`[data-metric-key="${key}"] strong`);
        if (element) element.textContent = fixture ? fixtureMetricFallback[key] : reportMetrics[key];
      }
      const thai = state.language === 'th';
      setText('report-validation-scope', thai
        ? fixture ? 'ตัวชี้วัดข้อมูลตัวอย่าง' : metadataOnly ? 'เงื่อนไขการประมวลผล' : 'ตัวชี้วัดข้อมูลอ้างอิงแบบอ่อน'
        : fixture ? 'Fixture metrics' : metadataOnly ? 'Processing gates' : 'Weak-reference candidate metrics');
      setText('report-validation-note', fixture
        ? thai ? 'ตัวชี้วัดนี้มาจากข้อมูลสังเคราะห์เท่านั้น การตรวจสอบน้ำท่วมจริงยังไม่สมบูรณ์' : 'Toy metrics are synthetic fixtures only. Real flood validation remains blocked.'
        : metadataOnly
          ? thai ? 'โหมดเมทาดาทาไม่แสดงข้ออ้างด้านความแม่นยำของการตัดสินใจ' : 'No decision accuracy claim is shown in metadata/blocker mode.'
          : thai ? 'ตัวชี้วัดผู้สมัครใช้ข้อมูลอ้างอิงแบบอ่อนที่วาดด้วยมือข้ามพรมแดน ไม่ใช่การตรวจสอบอย่างเป็นทางการหรือภาคสนาม' : 'Candidate metrics use a manually digitized cross-border weak reference. Not official validation or field validation.');
      setText('validation-summary-pre', fixture ? fixtureValidationSummary : metadataOnly ? (thai ? 'มุมมองเมทาดาทาและข้อจำกัด ซ่อนตัวชี้วัดการตัดสินใจของผู้สมัคร' : 'Metadata and blocker view. Candidate decision metrics are intentionally withheld.') : maeSaiValidationSummary);
      setText('report-brief-title', `${props.subdistrict_id} / ${localizedSubdistrictName(props)} (${metadataOnly ? (thai ? 'เมทาดาทาเท่านั้น' : 'metadata only') : `${thai ? 'ระดับ' : 'Class'} ${props.action_class || tr('common.unavailable')}`})`);
      setText('report-brief-focus', metadataOnly ? (thai ? 'ซ่อนข้อเสนอการตัดสินใจในโหมดข้อจำกัด' : 'Decision recommendation withheld in blocker view.') : `${thai ? 'จุดเน้นการตัดสินใจ' : 'Decision focus'}: ${localizedDecisionReason(props)}`);
      setText('report-brief-access', metadataOnly ? (thai ? 'ซ่อนค่าการสูญเสียการเข้าถึง' : 'Access-loss value withheld.') : `${thai ? 'ประชากรที่สูญเสียการเข้าถึงใน 30 นาทีจากแบบจำลอง' : 'Modeled 30-minute access loss'}: ${formatCompact(metrics.accessLoss)} ${thai ? 'คน' : 'people'}.`);
      setText('report-brief-warning', fixture ? (thai ? 'ข้อมูลตัวอย่างและไม่ใช่ระบบปฏิบัติการจริง ไม่ใช่คำเตือนภัยอย่างเป็นทางการ' : 'Fixture-backed and non-operational. Not an official warning.') : (thai ? 'การวิเคราะห์ด้วยข้อมูลอ้างอิงแบบอ่อน ไม่ได้ตรวจสอบภาคสนามและไม่ใช่คำเตือนภัยอย่างเป็นทางการ' : 'Weak-reference candidate analysis. Not field validated and not an official warning.'));
    }

    function updateModeChrome() {
      const fixture = state.datasetMode === 'fixture_demo';
      const metadata = state.datasetMode === 'metadata_blocker_view';
      const thai = state.language === 'th';
      const warning = document.getElementById('mode-warning');
      warning.className = `mode-warning ${metadata ? 'blocked' : fixture ? '' : 'weak-reference'}`.trim();
      setText('status-dataset', datasetLabel());
      setText('status-validation', thai
        ? fixture ? 'ยังไม่มีการตรวจสอบข้อมูลจริง' : metadata ? 'ยังไม่ผ่านเงื่อนไขประมวลผล' : 'ข้อมูลอ้างอิงแบบอ่อนเท่านั้น'
        : fixture ? 'Real validation blocked' : metadata ? 'Processing gated' : 'Weak reference only');
      setText('header-subtitle', fixture
        ? thai ? 'ศูนย์สาธิตการจัดลำดับความสำคัญในพื้นที่จากข้อมูลตัวอย่าง ไม่ใช่คำเตือนภัยอย่างเป็นทางการ' : 'Judge-demo command center for fixture-backed local prioritization. Not an official warning.'
        : thai ? 'หลักฐานผู้สมัครของแม่สายจาก Sentinel-1 และข้อมูลเปิดจริง ไม่ใช่ระบบปฏิบัติการจริง' : 'Mae Sai candidate decision evidence from real Sentinel-1 and open context. Non-operational.');
      setText('mode-warning-title', thai
        ? fixture ? 'การสาธิตด้วยข้อมูลตัวอย่าง' : metadata ? 'มุมมองเมทาดาทาและข้อจำกัด' : 'ข้อมูลอ้างอิงแบบอ่อน'
        : fixture ? 'Fixture demonstration' : metadata ? 'Metadata and blocker view' : 'Weak-reference candidate');
      setText('mode-warning-text', fixture
        ? thai ? 'ข้อมูลสังเคราะห์ใช้สาธิตการจัดลำดับและสถานการณ์เท่านั้น ไม่ได้ยืนยันความแม่นยำของการตรวจจับน้ำท่วมจริง' : 'Synthetic inputs demonstrate prioritization and scenarios; they do not establish real flood accuracy.'
        : metadata
          ? thai ? 'มีการบันทึกไฟล์และที่มาแล้ว แต่ยังไม่ผ่านเงื่อนไขการตรวจสอบอย่างเป็นทางการและการใช้งานจริง' : 'Files and provenance are documented, but official validation and operational processing remain gated.'
          : thai ? 'รวม Sentinel-1 และข้อมูลเปิดจริงแล้ว แต่ข้อมูลอ้างอิงใช้เพื่อปรับเทียบข้ามพรมแดนเท่านั้นและยังไม่ได้ตรวจสอบภาคสนาม' : 'Real Sentinel-1 and open context are joined. The manual reference is cross-border calibration only; results are not field validated.');
      setText('mode-warning-status', thai
        ? fixture ? 'ไม่ใช่ข้อมูลทางการ' : metadata ? 'ยังถูกจำกัด' : 'ไม่เป็นทางการ / ไม่ได้ตรวจสอบภาคสนาม'
        : fixture ? 'Not official' : metadata ? 'Blocked' : 'Not official / not field validated');
      setText('control-evidence-title', thai
        ? fixture ? 'ข้อมูลสังเคราะห์' : metadata ? 'คลังเมทาดาทา' : 'ข้อมูลจริงแบบผู้สมัคร'
        : fixture ? 'Synthetic fixture' : metadata ? 'Metadata inventory' : 'Real-data candidate');
      setText('control-evidence-note', fixture
        ? thai ? 'สถานการณ์จำลองพร้อมใช้งานสำหรับข้อมูลตัวอย่าง' : 'Scenario controls are available for the fixture workflow.'
        : metadata
          ? thai ? 'ซ่อนค่าการตัดสินใจ ใช้มุมมองนี้เพื่อตรวจสอบความพร้อม' : 'Decision values are withheld; use this view to inspect readiness.'
          : thai ? 'สถานการณ์จำลองยังไม่ได้ปรับเทียบกับชุดข้อมูลผู้สมัครจริง' : 'Scenarios are not yet calibrated for the real candidate dataset.');
      setText('map-title', thai
        ? fixture ? 'แผนที่ลำดับความสำคัญตัวอย่าง' : metadata ? 'ขอบเขตความพร้อมแม่สาย' : 'แผนที่ลำดับความสำคัญผู้สมัครแม่สาย'
        : fixture ? 'Fixture Priority Map' : metadata ? 'Mae Sai Readiness Footprint' : 'Mae Sai Candidate Priority Map');
      setText('map-subtitle', fixture
        ? thai ? 'รูปหลายเหลี่ยมลำดับความสำคัญและความเสี่ยงถนนสังเคราะห์จาก GeoJSON ที่ฝังในไฟล์' : 'Synthetic priority polygons and road-risk segments from embedded GeoJSON.'
        : metadata
          ? thai ? 'แสดงขอบเขตรายงาน COD-AB โดยไม่แสดงชั้นการตัดสินใจ' : 'Official COD-AB reporting boundaries shown without decision-layer overlays.'
          : thai ? 'แปดหน่วย ADM3 พร้อมความเสี่ยงถนนผู้สมัคร สถานที่จาก OSM และจุดสูญเสียการเข้าถึงจากแบบจำลอง' : 'Eight COD-AB ADM3 units with candidate road risk, OSM facilities, and modeled access hotspots.');
      setText('map-status-text', thai
        ? fixture ? 'ขั้นตอนการตัดสินใจจากข้อมูลตัวอย่าง' : metadata ? 'เมทาดาทาและขอบเขตรายงานเท่านั้น' : 'หลักฐานผู้สมัครจากข้อมูลอ้างอิงแบบอ่อน'
        : fixture ? 'Fixture-backed decision workflow' : metadata ? 'Metadata and reporting geometry only' : 'Weak-reference candidate evidence');
      document.getElementById('map-status-dot').className = `map-status-dot ${metadata ? 'blocked' : fixture ? '' : 'weak'}`.trim();
      document.getElementById('fixture-scenario-summary').hidden = !fixture;
      setText('panel-safety-note', fixture
        ? thai ? 'บริบทตัวอย่างเท่านั้น ไม่ใช่การตรวจจับน้ำท่วม การตรวจสอบ หรือคำเตือนภัยอย่างเป็นทางการ' : 'Fixture context only. Not flood detection, validation, or an official warning.'
        : metadata
          ? thai ? 'มุมมองเมทาดาทาเท่านั้น การประมวลผลและการตรวจสอบอย่างเป็นทางการยังถูกจำกัด' : 'Metadata-only view. Processing and official validation remain gated.'
          : thai ? 'การวิเคราะห์ด้วยข้อมูลอ้างอิงแบบอ่อน ไม่ใช่ระบบปฏิบัติการจริง ไม่ได้ตรวจสอบภาคสนาม และไม่ใช่คำเตือนภัยอย่างเป็นทางการ' : 'Weak-reference candidate analysis. Non-operational, not field validated, and not an official warning.');
      updateLegend();
      updateMapDetailStatus();
    }

    function updateLegend() {
      const fixture = state.datasetMode === 'fixture_demo';
      const metadata = state.datasetMode === 'metadata_blocker_view';
      const thai = state.language === 'th';
      setText('legend-primary-title', thai ? fixture ? 'ระดับการปฏิบัติ' : metadata ? 'ขอบเขตรายงาน' : 'FPPS ผู้สมัคร' : fixture ? 'Action class' : metadata ? 'Reporting geometry' : 'Candidate FPPS');
      setText('legend-secondary-title', thai ? fixture ? 'สถานการณ์และความเสี่ยงถนน' : metadata ? 'สถานะการประมวลผล' : 'บริบทผู้สมัคร' : fixture ? 'Scenario and road risk' : metadata ? 'Processing status' : 'Candidate context');
      const actionLegend = Object.entries(actionLabels[state.language])
        .map(([actionClass, label]) => `<span class="legend-item"><i class="swatch" style="background:${actionColors[actionClass]}"></i>${actionClass} ${escapeHtml(label)}</span>`)
        .join('');
      document.getElementById('legend-primary-items').innerHTML = fixture
        ? actionLegend
        : metadata
          ? '<span class="legend-item"><i class="swatch" style="background:#cbd5d1"></i>COD-AB ADM3 boundary</span>'
          : '<span class="legend-item"><i class="swatch" style="background:#b4533c"></i>FPPS ≥ 30</span><span class="legend-item"><i class="swatch" style="background:#d88736"></i>FPPS 20–29.9</span><span class="legend-item"><i class="swatch" style="background:#e2b33f"></i>FPPS 10–19.9</span><span class="legend-item"><i class="swatch" style="background:#6e9c88"></i>FPPS &lt; 10</span>';
      const facilityLegend = ['hospital', 'clinic', 'healthcare', 'school', 'shelter_candidate', 'emergency_service', 'community_facility']
        .map((type) => `<span class="legend-item facility-legend-row"><i class="facility-symbol ${type}"></i>${escapeHtml(facilityTypeLabel(type))}</span>`)
        .join('');
      document.getElementById('legend-secondary-items').innerHTML = fixture
        ? '<span class="legend-item"><i class="swatch" style="background:#167a55"></i>Delta improves</span><span class="legend-item"><i class="swatch" style="background:#c13f3f"></i>Delta worsens</span><span class="legend-item"><i class="road-sample"></i>High road risk</span><span class="legend-item"><i class="road-sample medium"></i>Medium road risk</span>'
        : metadata
          ? '<span class="legend-item"><i class="swatch" style="background:#c13f3f"></i>Official validation blocked</span>'
          : `<span class="legend-item"><i class="road-sample"></i>${thai ? 'อาจปิด' : 'Candidate closed'}</span><span class="legend-item"><i class="road-sample medium"></i>${thai ? 'อาจล่าช้า' : 'Candidate delayed'}</span>${facilityLegend}<span class="legend-item"><i class="marker-sample hotspot"></i>${thai ? 'จุดสูญเสียการเข้าถึงจากแบบจำลอง' : 'Modeled access hotspot'}</span>`;
    }

    function zoomToSelectedFeature() {
      const layer = featureLayers.get(state.selectedId);
      if (!layer) return;
      if (typeof layer.getBounds === 'function') {
        const bounds = layer.getBounds();
        map.fitBounds(bounds.pad(0.25));
        if (state.datasetMode === 'mae_sai_weak_reference' && map.getZoom() < semanticDetailZoom) {
          map.setView(bounds.getCenter(), semanticDetailZoom, { animate: false });
        }
      }
      layer.openPopup();
    }

    function priorityStyle(feature) {
      const props = feature.properties;
      const selected = String(props.subdistrict_id) === state.selectedId;
      const metadata = state.datasetMode === 'metadata_blocker_view';
      const realCandidate = state.datasetMode === 'mae_sai_weak_reference';
      const focusActive = state.focusSelected && Boolean(state.selectedId) && !metadata;
      const fillColor = metadata
        ? '#cbd5d1'
        : realCandidate
          ? maeSaiFppsColor(numeric(props.fpps_0_100, 0))
          : scenarioFillColor(props);
      return {
        color: selected ? '#10231e' : realCandidate ? '#4b5f57' : '#26352f',
        weight: selected ? 3 : 1.2,
        opacity: focusActive && !selected ? .38 : 1,
        fillColor,
        fillOpacity: metadata ? 0.22 : focusActive ? selected ? .72 : .16 : state.scenario === 'baseline' ? 0.52 : 0.64
      };
    }

    function maeSaiFppsColor(score) {
      if (score >= 30) return '#b4533c';
      if (score >= 20) return '#d88736';
      if (score >= 10) return '#e2b33f';
      return '#6e9c88';
    }

    function scenarioFillColor(props) {
      if (state.scenario === 'baseline') return actionColors[props.action_class] || actionColors.E;
      const value = scenarioDelta(props);
      if (value === null || value === 0) return deltaColors.neutral;
      return value < 0 ? deltaColors.improvement : deltaColors.worsening;
    }

    function scenarioDelta(props) {
      const field = state.scenario === 'temporary_shelter'
        ? 'temporary_shelter_change_people_losing_30_min_access'
        : 'road_closure_change_people_losing_30_min_access';
      const value = numeric(props[field], NaN);
      return Number.isFinite(value) ? value : null;
    }

    function roadStyle(feature) {
      const props = feature.properties || {};
      if (state.datasetMode === 'mae_sai_weak_reference') {
        const status = String(props.candidate_status || 'candidate_open_with_delay');
        return {
          color: status === 'candidate_closed' ? '#c13f3f' : status === 'candidate_delayed' ? '#cf6a32' : '#2d7b68',
          weight: status === 'candidate_closed' ? 4 : status === 'candidate_delayed' ? 2.8 : 1.4,
          opacity: status === 'candidate_open_with_delay' ? 0.42 : 0.82
        };
      }
      const risk = numeric(props.road_disruption_probability_0_1, 0);
      return { color: risk >= .7 ? '#c13f3f' : risk >= .5 ? '#cf6a32' : '#167a55', weight: 3 + risk * 4, opacity: .9 };
    }

    function accessHotspotPoint(feature, latlng) {
      const loss = numeric(feature.properties.people_losing_30_min_access, 0);
      return L.circleMarker(latlng, { radius: Math.min(14, 6 + Math.sqrt(loss) / 2), color: '#ffffff', weight: 2, fillColor: '#c13f3f', fillOpacity: .88 });
    }

    function priorityPopup(props) {
      const metrics = normalizedMetrics(props);
      const thai = state.language === 'th';
      return `<strong>${escapeHtml(props.subdistrict_id)} / ${escapeHtml(localizedSubdistrictName(props))}</strong><br>FPPS: ${escapeHtml(formatNumber(props.fpps_0_100, 2))}<br>${thai ? 'ระดับการปฏิบัติ' : 'Action'}: ${escapeHtml(props.action_class || tr('common.unavailable'))}<br>${thai ? 'สูญเสียการเข้าถึง 30 นาที' : '30-min access loss'}: ${escapeHtml(formatCompact(metrics.accessLoss))}<br><small>${thai ? 'หลักฐานผู้สมัครที่ไม่ใช่ระบบปฏิบัติการจริง' : 'Non-operational candidate evidence.'}</small>`;
    }

    function roadPopup(props) {
      const thai = state.language === 'th';
      return `<strong>${escapeHtml(props.road_name || props.road_id || (thai ? 'ถนนผู้สมัคร' : 'Road candidate'))}</strong><br>${thai ? 'สถานะ' : 'Status'}: ${escapeHtml(props.candidate_status || 'candidate risk')}<br>${thai ? 'ความเสี่ยง' : 'Risk'}: ${escapeHtml(formatNumber(props.road_disruption_probability_0_1, 3))}<br><small>${thai ? 'ไม่ใช่การปิดถนนที่สังเกตจริง' : 'Not an observed closure.'}</small>`;
    }

    function facilityPopup(props) {
      const thai = state.language === 'th';
      return `<strong>${escapeHtml(props.facility_name || facilityTypeLabel(props.facility_type))}</strong><br>${thai ? 'ประเภท' : 'Type'}: ${escapeHtml(facilityTypeLabel(props.facility_type))}<br>${thai ? 'สถานะ: ข้อมูลผู้สมัครจาก OSM ที่ยังไม่ได้ตรวจสอบ' : 'Status: unverified OSM candidate'}<br><small>${thai ? 'ไม่ใช่สถานที่ฉุกเฉินที่ได้รับการยืนยัน' : 'Not a confirmed emergency facility.'}</small>`;
    }

    function accessHotspotPopup(props) {
      const thai = state.language === 'th';
      const linked = featuresById.get(String(props.subdistrict_id))?.properties || props;
      return `<strong>${escapeHtml(props.subdistrict_id)} / ${escapeHtml(localizedSubdistrictName(linked))}</strong><br>${thai ? 'การสูญเสียการเข้าถึง 30 นาทีจากแบบจำลอง' : 'Modeled 30-min loss'}: ${escapeHtml(formatCompact(props.people_losing_30_min_access))}<br>${thai ? 'ช่องว่างความเสมอภาคโดยประมาณ' : 'Proxy equity gap'}: ${escapeHtml(formatNumber(props.equity_gap_ratio, 3))}<br><small>${thai ? 'ไม่ใช่การหยุดให้บริการที่สังเกตจริง' : 'Not an observed service outage.'}</small>`;
    }

    function currentBriefContent(props) {
      const brief = activeDataset().briefs[state.selectedId];
      if (brief) return brief;
      if (activeDataset().metadataOnly) return 'Metadata/blocker view does not generate action briefs.';
      return `# FloodGuard Candidate Summary - ${props.subdistrict_name || state.selectedId}\n\n- FPPS: ${formatNumber(props.fpps_0_100, 2)}\n- Action class: ${props.action_class || 'unavailable'}\n- Confidence: ${props.confidence_class || 'unavailable'}\n- Status: Non-operational. Not an official warning.\n`;
    }

    function updateClassPill(actionClass, metadataOnly) {
      const pill = document.getElementById('panel-detail-class');
      const color = metadataOnly ? '#7b8982' : (actionColors[actionClass] || '#7b8982');
      pill.style.color = color;
      pill.style.borderColor = color;
      pill.style.background = '#ffffff';
    }

    function escapeHtml(value) {
      return String(value ?? '')
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function numeric(value, fallback = NaN) {
      if (value === null || value === undefined || value === '') return fallback;
      const number = Number(value);
      return Number.isFinite(number) ? number : fallback;
    }

    function formatNumber(value, places) {
      const number = numeric(value, NaN);
      return Number.isFinite(number) ? number.toFixed(places) : tr('common.unavailable');
    }

    function formatCompact(value) {
      const number = numeric(value, NaN);
      if (!Number.isFinite(number)) return tr('common.unavailable');
      return new Intl.NumberFormat(state.language === 'th' ? 'th-TH' : 'en-US', { maximumFractionDigits: number < 10 ? 1 : 0 }).format(number);
    }

    function formatPercent(value) {
      const number = numeric(value, NaN);
      return Number.isFinite(number) ? `${(number * 100).toFixed(1)}%` : tr('common.unavailable');
    }

    function formatRatioPercent(value) {
      const number = numeric(value, NaN);
      if (!Number.isFinite(number)) return tr('common.unavailable');
      return `${number > 0 ? '+' : ''}${(number * 100).toFixed(1)}%`;
    }

    function formatSigned(value, places) {
      const number = numeric(value, NaN);
      if (!Number.isFinite(number)) return tr('common.unavailable');
      return `${number > 0 ? '+' : ''}${number.toFixed(places)}`;
    }

    function median(values) {
      if (!values.length) return NaN;
      const midpoint = Math.floor(values.length / 2);
      return values.length % 2 ? values[midpoint] : (values[midpoint - 1] + values[midpoint]) / 2;
    }

    function setText(elementId, value) {
      const element = document.getElementById(elementId);
      if (element) element.textContent = value;
    }

    function setDeltaBadge(elementId, value) {
      const element = document.getElementById(elementId);
      if (!element) return;
      const number = numeric(value, NaN);
      element.textContent = formatSigned(value, 0);
      element.classList.remove('good', 'bad');
      if (Number.isFinite(number) && number !== 0) element.classList.add(number < 0 ? 'good' : 'bad');
    }

    function downloadCurrentActionBrief() {
      const id = state.selectedId || 'selected';
      const feature = featuresById.get(id);
      const content = feature ? currentBriefContent(feature.properties) : `# FloodGuard Action Brief

No selected decision unit.
`;
      downloadText(`${state.datasetMode}_action_brief_${sanitizeFilename(id)}.md`, content, 'text/markdown;charset=utf-8');
    }

    function downloadFilteredGeoJSON() {
      const filtered = {
        type: 'FeatureCollection',
        features: (activeDataset().priority.features || []).filter((feature) =>
          state.visibleClasses.has(String(feature.properties.action_class))
        )
      };
      downloadText(`${state.datasetMode}_priority_filtered.geojson`, JSON.stringify(filtered, null, 2), 'application/geo+json;charset=utf-8');
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
    window.addEventListener('resize', preserveMapViewAfterLayout);
    if ('ResizeObserver' in window) {
      const mapPanel = document.querySelector('.map-panel');
      if (mapPanel) {
        new ResizeObserver(preserveMapViewAfterLayout).observe(mapPanel);
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
        "__FIXTURE_VALIDATION_METRICS_JSON__": json.dumps(
            validation_metric_cards,
            ensure_ascii=False,
        ),
        "__MAE_SAI_VALIDATION_SUMMARY_JSON__": json.dumps(
            mae_sai_validation_summary,
            ensure_ascii=False,
        ),
        "__FIXTURE_VALIDATION_SUMMARY_JSON__": json.dumps(
            validation_summary,
            ensure_ascii=False,
        ),
        "__MAE_SAI_WEAK_JSON__": json.dumps(
            mae_sai_weak_summary,
            ensure_ascii=False,
        ),
        "__MAE_SAI_PRIORITY_JSON__": json.dumps(
            mae_sai_priority_geojson,
            ensure_ascii=False,
        ),
        "__MAE_SAI_ROAD_JSON__": json.dumps(
            mae_sai_road_risk_geojson,
            ensure_ascii=False,
        ),
        "__MAE_SAI_FACILITY_JSON__": json.dumps(
            mae_sai_facilities_geojson,
            ensure_ascii=False,
        ),
        "__MAE_SAI_ACCESS_HOTSPOT_JSON__": json.dumps(
            mae_sai_access_hotspots_geojson,
            ensure_ascii=False,
        ),
        "__MAE_SAI_CONTEXT_QUALITY_JSON__": json.dumps(
            mae_sai_context_quality,
            ensure_ascii=False,
        ),
        "__MAE_SAI_SAR_CONTEXT_JSON__": json.dumps(
            mae_sai_sar_context,
            ensure_ascii=False,
        ),
        "__MAE_SAI_BRIEFS_JSON__": json.dumps(
            mae_sai_action_briefs,
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
    def _feature_score(feature: dict[str, Any]) -> float:
        properties = feature.get("properties") or {}
        try:
            return float(properties.get("fpps_0_100", float("-inf")))
        except (TypeError, ValueError):
            return float("-inf")

    selected_feature = max(features, key=_feature_score)
    props = selected_feature.get("properties") or {}
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
        f"{summary.get('feature_count')} ADM3 reporting units; the highest-FPPS "
        "unit has FPPS "
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
    metric_keys = ("iou", "f1_dice", "precision", "recall", "area_error")
    return "".join(
        [
            f'<div class="validation-metric" data-metric-key="{metric_keys[index]}">'
            f"<span>{html.escape(card['label'])}</span>"
            f"<strong>{html.escape(card['value'])}</strong>"
            "</div>"
            for index, card in enumerate(cards)
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
