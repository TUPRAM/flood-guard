"""Static dashboard writer for fixture-backed FloodGuard outputs."""

from __future__ import annotations

from collections.abc import Sequence
import html
import json
from pathlib import Path
from typing import Any


class DashboardError(ValueError):
    """Raised when dashboard inputs violate the dashboard contract."""


ActionBriefPaths = str | Path | Sequence[str | Path]


def write_static_dashboard(
    priority_geojson_path: str | Path,
    road_risk_geojson_path: str | Path,
    validation_summary_path: str | Path,
    action_brief_path: ActionBriefPaths,
    output_path: str | Path,
) -> Path:
    """Write a standalone HTML dashboard with embedded GeoJSON and Markdown."""

    priority_geojson = _read_feature_collection(priority_geojson_path, "priority")
    road_risk_geojson = _read_feature_collection(road_risk_geojson_path, "road_risk")
    validation_summary = Path(validation_summary_path).read_text(encoding="utf-8")
    action_briefs = _read_action_briefs(action_brief_path)

    top_priority = _select_top_actionable(priority_geojson)
    html_text = _build_dashboard_html(
        priority_geojson=priority_geojson,
        road_risk_geojson=road_risk_geojson,
        validation_summary=validation_summary,
        action_briefs=action_briefs,
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
) -> str:
    props = top_priority.get("properties") or {}
    template = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FloodGuard Static Dashboard</title>
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
    }
    .toolbar label {
      display: flex;
      align-items: center;
      gap: 6px;
      white-space: nowrap;
    }
    #map {
      min-height: 460px;
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
      padding: 18px 22px 28px;
      background: var(--panel);
    }
    .doc-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }
    pre {
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
    }
    .note {
      font-size: 12px;
      color: var(--muted);
      margin-top: 12px;
    }
    @media (max-width: 900px) {
      .shell { display: block; }
      aside {
        border-right: 0;
        border-bottom: 1px solid var(--line);
      }
      .doc-grid { grid-template-columns: 1fr; }
      .legend { grid-template-columns: 1fr 1fr; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <h1>FloodGuard Decision Dashboard</h1>
      <p>Fixture-backed prototype for local prioritization. Not an official warning.</p>
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
      </div>
      <div class="metric-grid">
        <div class="metric"><span class="label">Selected</span><span class="value" id="panel-subdistrict">__TOP_SUBDISTRICT__</span></div>
        <div class="metric"><span class="label">Class</span><span class="value" id="panel-class">__TOP_CLASS__</span></div>
        <div class="metric"><span class="label">FPPS</span><span class="value" id="panel-fpps">__TOP_FPPS__</span></div>
        <div class="metric"><span class="label">Confidence</span><span class="value" id="panel-confidence">__TOP_CONFIDENCE__</span></div>
      </div>
      <h2>Access and Equity</h2>
      <ul class="summary-list">
        <li>Baseline 30-min access loss: <strong id="panel-baseline-access">__TOP_BASELINE_ACCESS__</strong></li>
        <li>Baseline equity gap ratio: <strong id="panel-baseline-equity">__TOP_BASELINE_EQUITY__</strong></li>
        <li>Temporary shelter 30-min change: <span class="delta-badge" id="panel-temp-delta">__TOP_TEMP_DELTA__</span></li>
        <li>Road closure 30-min change: <span class="delta-badge" id="panel-road-delta">__TOP_ROAD_DELTA__</span></li>
      </ul>
      <h2>Decision Note</h2>
      <p id="panel-reason">__TOP_REASON__</p>
      <p class="note">Scenario colors show people losing 30-minute access: green improves, red worsens, gray is neutral or unavailable.</p>
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
        <span><i class="swatch" style="background:#21835f"></i>Delta improves</span>
        <span><i class="swatch" style="background:#b73c3c"></i>Delta worsens</span>
        <span><i class="swatch" style="background:#7f8a82"></i>Neutral/unavailable</span>
      </section>
    </main>
  </div>
  <section class="docs">
    <div class="doc-grid">
      <article id="validation-summary">
        <h2>Validation Summary</h2>
        <pre>__VALIDATION_SUMMARY__</pre>
      </article>
      <article id="action-brief">
        <h2>Action Brief</h2>
        <pre id="action-brief-pre">__INITIAL_BRIEF__</pre>
      </article>
    </div>
  </section>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const priorityData = __PRIORITY_JSON__;
    const roadRiskData = __ROAD_JSON__;
    const briefsBySubdistrict = __BRIEFS_JSON__;
    const actionColors = {
      A: '#b73c3c',
      B: '#d36a35',
      C: '#d8a629',
      D: '#21835f',
      E: '#6d5aa8'
    };
    const deltaColors = {
      improvement: '#21835f',
      worsening: '#b73c3c',
      neutral: '#7f8a82'
    };
    const state = {
      selectedId: '__TOP_ID__',
      scenario: 'baseline',
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
      document.getElementById('toggle-priority').addEventListener('change', (event) => {
        state.showPriority = event.target.checked;
        state.showPriority ? priorityLayer.addTo(map) : priorityLayer.removeFrom(map);
      });
      document.getElementById('toggle-roads').addEventListener('change', (event) => {
        state.showRoads = event.target.checked;
        state.showRoads ? roadLayer.addTo(map) : roadLayer.removeFrom(map);
      });
    }

    function bindPriorityFeature(feature, layer) {
      const id = String(feature.properties.subdistrict_id);
      featureLayers.set(id, layer);
      layer.bindPopup(popup(feature.properties));
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
      document.getElementById('panel-subdistrict').textContent = `${props.subdistrict_id}`;
      document.getElementById('panel-class').textContent = props.action_class || 'unavailable';
      document.getElementById('panel-fpps').textContent = formatNumber(props.fpps_0_100, 2);
      document.getElementById('panel-confidence').textContent = props.confidence_class || 'unavailable';
      document.getElementById('panel-baseline-access').textContent = formatNumber(props.baseline_people_losing_30_min_access, 0);
      document.getElementById('panel-baseline-equity').textContent = formatNumber(props.baseline_equity_gap_ratio, 3);
      setDeltaBadge('panel-temp-delta', props.temporary_shelter_change_people_losing_30_min_access);
      setDeltaBadge('panel-road-delta', props.road_closure_change_people_losing_30_min_access);
      document.getElementById('panel-reason').textContent = props.top_reason || '';
      document.getElementById('action-brief-pre').textContent =
        briefsBySubdistrict[state.selectedId] || 'No generated action brief for this subdistrict.';
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
        .map(([key, value]) => `<strong>${key}</strong>: ${value ?? 'unavailable'}`)
        .join('<br>');
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

    function setDeltaBadge(elementId, value) {
      const element = document.getElementById(elementId);
      const number = Number(value);
      element.textContent = formatSigned(value, 0);
      element.classList.remove('good', 'bad');
      if (!Number.isFinite(number) || number === 0) {
        return;
      }
      element.classList.add(number < 0 ? 'good' : 'bad');
    }

    initializeDashboardControls();
    renderPriorityLayer();
    updateSelectedPanel();
    const bounds = priorityLayer.getBounds();
    if (bounds.isValid()) {
      map.fitBounds(bounds.pad(0.18));
    } else {
      map.setView([18.02, 100.02], 13);
    }
  </script>
</body>
</html>
"""

    top_id = str(props.get("subdistrict_id", ""))
    initial_brief = action_briefs.get(top_id) or next(iter(action_briefs.values()))
    replacements = {
        "__PRIORITY_JSON__": json.dumps(priority_geojson, ensure_ascii=False),
        "__ROAD_JSON__": json.dumps(road_risk_geojson, ensure_ascii=False),
        "__BRIEFS_JSON__": json.dumps(action_briefs, ensure_ascii=False),
        "__VALIDATION_SUMMARY__": html.escape(validation_summary),
        "__INITIAL_BRIEF__": html.escape(initial_brief),
        "__TOP_ID__": _js_string(top_id),
        "__TOP_SUBDISTRICT__": html.escape(top_id),
        "__TOP_CLASS__": html.escape(str(props.get("action_class", ""))),
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


def _format_signed(value: object, places: int) -> str:
    try:
        numeric = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "unavailable"
    sign = "+" if numeric > 0 else ""
    return f"{sign}{numeric:.{places}f}"


def _js_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)[1:-1]
