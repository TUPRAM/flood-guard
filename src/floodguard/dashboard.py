"""Static dashboard writer for fixture-backed FloodGuard outputs."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


class DashboardError(ValueError):
    """Raised when dashboard inputs violate the dashboard contract."""


def write_static_dashboard(
    priority_geojson_path: str | Path,
    road_risk_geojson_path: str | Path,
    validation_summary_path: str | Path,
    action_brief_path: str | Path,
    output_path: str | Path,
) -> Path:
    """Write a standalone HTML dashboard with embedded GeoJSON and Markdown."""

    priority_geojson = _read_feature_collection(priority_geojson_path, "priority")
    road_risk_geojson = _read_feature_collection(road_risk_geojson_path, "road_risk")
    validation_summary = Path(validation_summary_path).read_text(encoding="utf-8")
    action_brief = Path(action_brief_path).read_text(encoding="utf-8")

    top_priority = _select_top_actionable(priority_geojson)
    html_text = _build_dashboard_html(
        priority_geojson=priority_geojson,
        road_risk_geojson=road_risk_geojson,
        validation_summary=validation_summary,
        action_brief=action_brief,
        top_priority=top_priority,
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
    action_brief: str,
    top_priority: dict[str, Any],
) -> str:
    props = top_priority.get("properties") or {}
    priority_json = json.dumps(priority_geojson, ensure_ascii=False)
    road_json = json.dumps(road_risk_geojson, ensure_ascii=False)
    validation_html = html.escape(validation_summary)
    brief_html = html.escape(action_brief)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FloodGuard Static Dashboard</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8f4;
      --panel: #ffffff;
      --ink: #202722;
      --muted: #5b665f;
      --line: #d8ded4;
      --green: #21835f;
      --yellow: #d8a629;
      --orange: #d36a35;
      --red: #b73c3c;
      --violet: #6d5aa8;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Arial, Helvetica, sans-serif;
      line-height: 1.45;
    }}
    .shell {{
      min-height: 100vh;
      display: grid;
      grid-template-columns: minmax(320px, 390px) minmax(0, 1fr);
    }}
    aside {{
      background: var(--panel);
      border-right: 1px solid var(--line);
      padding: 22px;
      overflow-y: auto;
    }}
    main {{
      min-width: 0;
      display: grid;
      grid-template-rows: minmax(440px, 64vh) auto;
    }}
    h1, h2, h3 {{
      margin: 0;
      line-height: 1.15;
      letter-spacing: 0;
    }}
    h1 {{
      font-size: 24px;
      margin-bottom: 8px;
    }}
    h2 {{
      font-size: 16px;
      margin-top: 22px;
      margin-bottom: 10px;
    }}
    h3 {{
      font-size: 14px;
      margin-bottom: 8px;
    }}
    p {{
      margin: 0 0 12px;
      color: var(--muted);
      font-size: 14px;
    }}
    .metric-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin: 16px 0;
    }}
    .metric {{
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      background: #fbfcf8;
    }}
    .label {{
      display: block;
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0;
      margin-bottom: 4px;
    }}
    .value {{
      font-size: 20px;
      font-weight: 700;
    }}
    .summary-list {{
      padding: 0;
      margin: 0;
      list-style: none;
      display: grid;
      gap: 8px;
      font-size: 14px;
    }}
    .summary-list li {{
      border-top: 1px solid var(--line);
      padding-top: 8px;
    }}
    .toolbar {{
      position: absolute;
      top: 14px;
      right: 14px;
      z-index: 500;
      background: rgba(255, 255, 255, .96);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 10px;
      display: flex;
      gap: 12px;
      font-size: 13px;
      box-shadow: 0 8px 20px rgba(32, 39, 34, .08);
    }}
    .toolbar label {{
      display: flex;
      align-items: center;
      gap: 6px;
      white-space: nowrap;
    }}
    #map {{
      min-height: 440px;
      width: 100%;
      position: relative;
    }}
    .map-wrap {{
      position: relative;
      min-width: 0;
    }}
    .legend {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 8px;
      padding: 12px 16px;
      border-top: 1px solid var(--line);
      background: var(--panel);
      font-size: 12px;
    }}
    .legend span {{
      display: flex;
      align-items: center;
      gap: 6px;
      min-width: 0;
    }}
    .swatch {{
      width: 12px;
      height: 12px;
      border-radius: 3px;
      border: 1px solid rgba(32, 39, 34, .2);
      flex: 0 0 auto;
    }}
    .docs {{
      border-top: 1px solid var(--line);
      padding: 18px 22px 28px;
      background: var(--panel);
    }}
    .doc-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }}
    pre {{
      margin: 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      background: #f6f7f1;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 12px;
      max-height: 360px;
      overflow: auto;
      font: 12px/1.45 Consolas, Monaco, monospace;
      color: #263027;
    }}
    .note {{
      font-size: 12px;
      color: var(--muted);
      margin-top: 12px;
    }}
    @media (max-width: 860px) {{
      .shell {{
        display: block;
      }}
      aside {{
        border-right: 0;
        border-bottom: 1px solid var(--line);
      }}
      .doc-grid {{
        grid-template-columns: 1fr;
      }}
      .legend {{
        grid-template-columns: 1fr 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <h1>FloodGuard Decision Dashboard</h1>
      <p>Fixture-backed prototype for local prioritization. Not an official warning.</p>
      <div class="metric-grid">
        <div class="metric"><span class="label">Top actionable</span><span class="value">{html.escape(str(props.get("subdistrict_id", "")))}</span></div>
        <div class="metric"><span class="label">Class</span><span class="value">{html.escape(str(props.get("action_class", "")))}</span></div>
        <div class="metric"><span class="label">FPPS</span><span class="value">{_format_number(props.get("fpps_0_100"), 2)}</span></div>
        <div class="metric"><span class="label">Confidence</span><span class="value">{html.escape(str(props.get("confidence_class", "")))}</span></div>
      </div>
      <h2>Access and Equity</h2>
      <ul class="summary-list">
        <li>Baseline 30-min access loss: <strong>{_format_number(props.get("baseline_people_losing_30_min_access"), 0)}</strong></li>
        <li>Baseline equity gap ratio: <strong>{_format_number(props.get("baseline_equity_gap_ratio"), 3)}</strong></li>
        <li>Temporary shelter 30-min change: <strong>{_format_signed(props.get("temporary_shelter_change_people_losing_30_min_access"), 0)}</strong></li>
        <li>Road closure 30-min change: <strong>{_format_signed(props.get("road_closure_change_people_losing_30_min_access"), 0)}</strong></li>
      </ul>
      <h2>Decision Note</h2>
      <p>{html.escape(str(props.get("top_reason", "")))}</p>
      <p class="note">Scenario comparison fields are embedded in priority_subdistricts.geojson.</p>
    </aside>
    <main>
      <section class="map-wrap" aria-label="FloodGuard map">
        <div class="toolbar" aria-label="Layer toggles">
          <label><input id="toggle-priority" type="checkbox" checked> Priority</label>
          <label><input id="toggle-roads" type="checkbox" checked> Road risk</label>
        </div>
        <div id="map"></div>
      </section>
      <section class="legend" aria-label="Legend">
        <span><i class="swatch" style="background:#b73c3c"></i>A Protect Lives</span>
        <span><i class="swatch" style="background:#d36a35"></i>B Routes</span>
        <span><i class="swatch" style="background:#d8a629"></i>C Services</span>
        <span><i class="swatch" style="background:#21835f"></i>D Resilience</span>
        <span><i class="swatch" style="background:#6d5aa8"></i>E Monitor</span>
      </section>
    </main>
  </div>
  <section class="docs">
    <div class="doc-grid">
      <article id="validation-summary">
        <h2>Validation Summary</h2>
        <pre>{validation_html}</pre>
      </article>
      <article id="action-brief">
        <h2>Action Brief</h2>
        <pre>{brief_html}</pre>
      </article>
    </div>
  </section>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const priorityData = {priority_json};
    const roadRiskData = {road_json};
    const actionColors = {{
      A: '#b73c3c',
      B: '#d36a35',
      C: '#d8a629',
      D: '#21835f',
      E: '#6d5aa8'
    }};

    const map = L.map('map', {{ scrollWheelZoom: false }});
    L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors'
    }}).addTo(map);

    function priorityStyle(feature) {{
      const cls = feature.properties.action_class || 'E';
      return {{
        color: '#202722',
        weight: 1,
        fillColor: actionColors[cls] || actionColors.E,
        fillOpacity: 0.45
      }};
    }}

    function roadStyle(feature) {{
      const risk = Number(feature.properties.road_disruption_probability_0_1 || 0);
      return {{
        color: risk >= 0.7 ? '#b73c3c' : risk >= 0.5 ? '#d36a35' : '#21835f',
        weight: 3 + risk * 4,
        opacity: 0.9
      }};
    }}

    function popup(properties) {{
      return Object.entries(properties)
        .map(([key, value]) => `<strong>${{key}}</strong>: ${{value ?? 'unavailable'}}`)
        .join('<br>');
    }}

    const priorityLayer = L.geoJSON(priorityData, {{
      style: priorityStyle,
      onEachFeature: (feature, layer) => layer.bindPopup(popup(feature.properties))
    }}).addTo(map);

    const roadLayer = L.geoJSON(roadRiskData, {{
      style: roadStyle,
      onEachFeature: (feature, layer) => layer.bindPopup(popup(feature.properties))
    }}).addTo(map);

    const bounds = priorityLayer.getBounds();
    if (bounds.isValid()) {{
      map.fitBounds(bounds.pad(0.18));
    }} else {{
      map.setView([18.02, 100.02], 13);
    }}

    document.getElementById('toggle-priority').addEventListener('change', (event) => {{
      event.target.checked ? priorityLayer.addTo(map) : priorityLayer.removeFrom(map);
    }});
    document.getElementById('toggle-roads').addEventListener('change', (event) => {{
      event.target.checked ? roadLayer.addTo(map) : roadLayer.removeFrom(map);
    }});
  </script>
</body>
</html>
"""


def _format_number(value: object, places: int) -> str:
    try:
        numeric = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "unavailable"
    return f"{numeric:.{places}f}"


def _format_signed(value: object, places: int) -> str:
    try:
        numeric = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "unavailable"
    sign = "+" if numeric > 0 else ""
    return f"{sign}{numeric:.{places}f}"
