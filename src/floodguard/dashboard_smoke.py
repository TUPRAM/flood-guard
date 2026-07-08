"""Dependency-light smoke checks for the static FloodGuard dashboard."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
from threading import Thread
from typing import Iterator
from urllib.error import URLError
from urllib.request import Request, urlopen


DEFAULT_VIEWPORTS: tuple[tuple[str, int, int], ...] = (
    ("judge_frame", 1536, 1024),
    ("large_monitor", 2048, 1152),
    ("laptop", 1440, 900),
)

OSM_TILE_PROBE_URL = "https://tile.openstreetmap.org/12/3184/1849.png"


@dataclass(frozen=True)
class DashboardSmokeCheck:
    """One smoke-check result."""

    name: str
    passed: bool
    detail: str


class DashboardSmokeError(RuntimeError):
    """Raised when dashboard smoke checks cannot run."""


class _QuietSimpleHTTPRequestHandler(SimpleHTTPRequestHandler):
    """Static-file handler that keeps smoke-check output readable."""

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


def run_dashboard_smoke_checks(
    dashboard_path: str | Path,
    *,
    check_network_tiles: bool = False,
) -> list[DashboardSmokeCheck]:
    """Run static and local-server smoke checks for ``outputs/dashboard.html``.

    The smoke suite intentionally avoids browser and build dependencies by default.
    It starts a local static server, fetches the dashboard through HTTP, and checks
    for the dashboard landmarks that protect the judge-demo layout from regressing.
    """

    dashboard = Path(dashboard_path)
    if not dashboard.exists():
        raise DashboardSmokeError(f"Dashboard does not exist: {dashboard}")
    if dashboard.name != "dashboard.html":
        raise DashboardSmokeError("Dashboard smoke check expects a dashboard.html file.")

    html = dashboard.read_text(encoding="utf-8")
    checks = _static_checks(html)

    with serve_directory(dashboard.parent) as base_url:
        served_url = f"{base_url}/{dashboard.name}"
        served_html = _read_url(served_url)
        checks.append(
            DashboardSmokeCheck(
                "local_static_server_fetch",
                "FloodGuard Decision Dashboard" in served_html,
                f"Fetched {served_url}",
            )
        )

    if check_network_tiles:
        checks.append(_check_tile_probe())
    else:
        checks.append(
            DashboardSmokeCheck(
                "leaflet_tile_probe",
                True,
                "Skipped network tile probe; Leaflet and OpenStreetMap tile configuration is present.",
            )
        )

    return checks


def smoke_checks_passed(checks: list[DashboardSmokeCheck]) -> bool:
    """Return ``True`` when every smoke check passed."""

    return all(check.passed for check in checks)


def format_smoke_report(checks: list[DashboardSmokeCheck]) -> str:
    """Format smoke checks as a compact Markdown table."""

    lines = [
        "# FloodGuard Dashboard Smoke Check",
        "",
        "| Check | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for check in checks:
        status = "PASS" if check.passed else "FAIL"
        lines.append(f"| `{check.name}` | {status} | {_escape_table(check.detail)} |")
    lines.append("")
    lines.append(f"Overall: {'PASS' if smoke_checks_passed(checks) else 'FAIL'}")
    return "\n".join(lines)


@contextmanager
def serve_directory(directory: str | Path) -> Iterator[str]:
    """Serve a directory on a local ephemeral port for smoke checks."""

    root = Path(directory).resolve()
    if not root.exists():
        raise DashboardSmokeError(f"Serve directory does not exist: {root}")
    handler = partial(_QuietSimpleHTTPRequestHandler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _static_checks(html: str) -> list[DashboardSmokeCheck]:
    checks = [
        _contains(
            html,
            "page_title",
            "<title>FloodGuard Static Dashboard</title>",
            "Dashboard title is present.",
        ),
        _contains(
            html,
            "dashboard_identity",
            "FloodGuard Decision Dashboard",
            "App header identity is present.",
        ),
        _contains(
            html,
            "static_no_backend_claim",
            "Static HTML | embedded data | no backend",
            "Static no-backend wording is present.",
        ),
        _absent(
            html,
            "no_fetch_dependency",
            "fetch(",
            "No browser-side fetch call found.",
        ),
        _contains(
            html,
            "leaflet_css",
            "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css",
            "Leaflet CSS CDN reference is present.",
        ),
        _contains(
            html,
            "leaflet_js",
            "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js",
            "Leaflet JS CDN reference is present.",
        ),
        _contains(
            html,
            "osm_tile_layer",
            "tile.openstreetmap.org",
            "OpenStreetMap tile layer is configured.",
        ),
        _contains(
            html,
            "embedded_priority_geojson",
            "const priorityData =",
            "Priority GeoJSON is embedded.",
        ),
        _contains(
            html,
            "embedded_road_risk_geojson",
            "const roadRiskData =",
            "Road-risk GeoJSON is embedded.",
        ),
        _contains(
            html,
            "priority_polygon_renderer",
            "priorityLayer.addData(visibleFeatures)",
            "Priority polygons are rendered from filtered embedded data.",
        ),
        _contains(
            html,
            "road_risk_renderer",
            "L.geoJSON(roadRiskData",
            "Road-risk segments are rendered from embedded data.",
        ),
        _contains(
            html,
            "label_overlap_guard",
            "width: 74px",
            "Subdistrict label width guard is present.",
        ),
        _contains(
            html,
            "label_escape_guard",
            "escapeHtml(id)",
            "Subdistrict label text is escaped.",
        ),
        _contains(
            html,
            "map_viewport_safe_sizing",
            "height: clamp(500px, calc(100vh - 390px), 540px)",
            "Map workspace has explicit viewport-safe sizing.",
        ),
        _contains(
            html,
            "leaflet_invalidate_size",
            "map.invalidateSize",
            "Leaflet resize guard is present.",
        ),
        _contains(
            html,
            "validation_cards_visible",
            'class="validation-metric-grid"',
            "Validation metric cards are present.",
        ),
        _contains(
            html,
            "brief_summary_visible",
            'class="brief-summary"',
            "Action brief summary is present.",
        ),
        _contains(
            html,
            "export_current_brief",
            'id="download-current-brief"',
            "Current-brief export button is present.",
        ),
        _contains(
            html,
            "export_filtered_geojson",
            'id="download-filtered-geojson"',
            "Filtered-GeoJSON export button is present.",
        ),
        _contains(
            html,
            "non_operational_wording",
            "not an official warning",
            "Non-operational warning wording is present.",
        ),
        _contains(
            html,
            "real_validation_blocked_wording",
            "Real validation blocked",
            "Real-validation blocked wording is present.",
        ),
        _absent(
            html,
            "no_windows_absolute_paths_backslash",
            "C:\\Users",
            "No Windows absolute source paths are exposed.",
        ),
        _absent(
            html,
            "no_windows_absolute_paths_slash",
            "C:/Users",
            "No slash-style Windows absolute source paths are exposed.",
        ),
    ]
    checks.append(_check_priority_feature_count(html))
    checks.append(_check_label_count(html))
    return checks


def _check_priority_feature_count(html: str) -> DashboardSmokeCheck:
    match = re.search(r"const priorityData = (\{.*?\});\n\s*const roadRiskData", html, re.S)
    if not match:
        return DashboardSmokeCheck(
            "priority_feature_count",
            False,
            "Could not locate embedded priorityData.",
        )
    feature_count = match.group(1).count('"type": "Feature"')
    return DashboardSmokeCheck(
        "priority_feature_count",
        feature_count >= 5,
        f"Found {feature_count} embedded priority features.",
    )


def _check_label_count(html: str) -> DashboardSmokeCheck:
    required = ("FG-TB-001", "FG-TB-002", "FG-TB-003")
    missing = [label for label in required if label not in html]
    return DashboardSmokeCheck(
        "subdistrict_labels_present",
        not missing,
        (
            "Required first-viewport labels are present."
            if not missing
            else f"Missing label(s): {', '.join(missing)}"
        ),
    )


def _check_tile_probe() -> DashboardSmokeCheck:
    try:
        request = Request(
            OSM_TILE_PROBE_URL,
            headers={"User-Agent": "FloodGuard dashboard smoke check"},
        )
        with urlopen(request, timeout=10) as response:
            content_type = response.headers.get("Content-Type", "")
            ok = response.status == 200 and "image" in content_type
            return DashboardSmokeCheck(
                "leaflet_tile_probe",
                ok,
                f"HTTP {response.status}; content-type={content_type}",
            )
    except URLError as exc:
        return DashboardSmokeCheck(
            "leaflet_tile_probe",
            False,
            f"Tile probe failed: {exc}",
        )


def _read_url(url: str) -> str:
    request = Request(url, headers={"User-Agent": "FloodGuard dashboard smoke check"})
    try:
        with urlopen(request, timeout=10) as response:
            return response.read().decode("utf-8")
    except URLError as exc:
        raise DashboardSmokeError(f"Could not fetch {url}: {exc}") from exc


def _contains(
    html: str,
    name: str,
    needle: str,
    detail: str,
) -> DashboardSmokeCheck:
    return DashboardSmokeCheck(name, needle in html, detail)


def _absent(
    html: str,
    name: str,
    needle: str,
    detail: str,
) -> DashboardSmokeCheck:
    return DashboardSmokeCheck(name, needle not in html, detail)


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
