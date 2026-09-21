"""Local-only, source-clock plots and review tables for candidate evidence."""

from __future__ import annotations

import calendar
import csv
import html
import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


def _escape(value: Any) -> str:
    if value is None or value == "":
        return "Unavailable"
    if isinstance(value, (list, tuple)):
        value = "; ".join(str(item) for item in value)
    return html.escape(str(value), quote=True)


def _json(path: Path, fallback: Any) -> Any:
    return (
        json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else fallback
    )


def _csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _table(rows: list[dict], fields: list[tuple[str, str]]) -> str:
    if not rows:
        return '<p class="empty">No records available for this review.</p>'
    headings = "".join(f"<th>{_escape(label)}</th>" for _, label in fields)
    body = "".join(
        "<tr>"
        + "".join(f"<td>{_escape(row.get(key))}</td>" for key, _ in fields)
        + "</tr>"
        for row in rows
    )
    return f'<div class="table-scroll"><table><thead><tr>{headings}</tr></thead><tbody>{body}</tbody></table></div>'


def _memberships(value: Any) -> list[str]:
    if isinstance(value, list):
        return value
    try:
        decoded = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return decoded if isinstance(decoded, list) else []


def _plot(series: dict, units: str) -> str:
    """Render each contiguous observed segment independently, without interpolation."""
    parsed = []
    for segment in series.get("segments", []):
        valid = []
        for timestamp, value in segment:
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(
                    "Hydrograph segments must contain only finite observations"
                )
            time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if valid and (time - valid[-1][0]).total_seconds() != 600:
                raise ValueError(
                    "Hydrograph segment crosses a missing or non-ten-minute slot"
                )
            valid.append((time, value))
        if valid:
            parsed.append(valid)
    if not parsed:
        return '<p class="empty">No usable numeric observations. The missing series is not a zero-level line.</p>'
    points = [point for segment in parsed for point in segment]
    month = str(series["month"]).replace("-", "")
    year, number = int(month[:4]), int(month[4:6])
    start = datetime(year, number, 1, tzinfo=points[0][0].tzinfo)
    end = start + timedelta(days=calendar.monthrange(year, number)[1])
    if any(not start <= time < end for time, _ in points):
        raise ValueError(
            "Hydrograph observation lies outside its declared source month"
        )
    lower = min(value for _, value in points)
    upper = max(value for _, value in points)

    def position(point: tuple[datetime, float]) -> tuple[float, float]:
        return (
            65
            + (point[0] - start).total_seconds() / (end - start).total_seconds() * 835,
            185 - (point[1] - lower) / (upper - lower or 1) * 140,
        )

    marks = []
    for segment in parsed:
        if len(segment) == 1:
            x, y = position(segment[0])
            marks.append(
                f'<circle data-observed-singleton="true" cx="{x:.1f}" cy="{y:.1f}" r="2.5"/>'
            )
        else:
            path = " ".join(
                f"{'M' if index == 0 else 'L'}{x:.1f},{y:.1f}"
                for index, point in enumerate(segment)
                for x, y in [position(point)]
            )
            marks.append(f'<path data-observed-segment="true" d="{path}"/>')
    label = f"{series['station_code']} {series['month']}: observed water-surface elevation; missing intervals are disconnected"
    return (
        f'<svg viewBox="0 0 940 230" role="img" aria-label="{_escape(label)}">'
        f'<title>{_escape(label)}</title><line x1="65" y1="185" x2="900" y2="185" stroke="#a7bac5"/>'
        f'<text x="8" y="47">{upper:.2f}</text><text x="8" y="187">{lower:.2f}</text>'
        f'<text x="65" y="217">{start.date().isoformat()}</text><text x="900" y="217" text-anchor="end">{end.date().isoformat()}</text>'
        f'<text x="65" y="22">{_escape(units)} · source clock; timezone unconfirmed</text>'
        '<g fill="none" stroke="#087e8b" stroke-width="1.5">'
        + "".join(marks)
        + "</g></svg>"
        f'<p class="small">Maximum observed: {upper:.3f} {_escape(units)}. This is not a verified event peak. '
        "Every normalized numeric observation is plotted; coordinates round to one display decimal. Each missing interval breaks the line.</p>"
    )


def render_local_report(output_dir: Path, registry: dict, summary: dict) -> Path:
    """Write a self-contained local research HTML report outside hosted assets.

    The report plots all normalized station-month series and uses selected,
    non-contact fields for facility review. It never copies raw source records
    or publishes data. Normalized-layer links stay relative to this report.
    """
    root = Path(output_dir).resolve()
    if {"apps", "web", "public"}.issubset({part.casefold() for part in root.parts}):
        raise ValueError(
            "Local evidence report must not be written under hosted public assets"
        )
    normalized = root / "normalized"
    datasets = summary.get("datasets", {})
    gauges = datasets.get("gauges", {})
    plots = _json(normalized / "gauge_hydrograph_segments.json", {"series": []})
    series = plots.get("series", [])
    if len(series) != gauges.get("station_month_files", len(series)):
        raise ValueError(
            "Local report hydrograph count differs from the normalized station-month inventory"
        )
    daily = _csv(normalized / "gauge_daily_coverage.csv")
    for row in daily:
        for key in ("missing_measurement", "absent_timestamp"):
            row[key] = row.get(key) or "0"
    station_months = gauges.get("station_months", [])
    monthly = {(row["station_code"], row["month"]): row for row in station_months}
    plot_keys = [(row["station_code"], row["month"]) for row in series]
    if len(set(plot_keys)) != len(plot_keys) or (
        monthly and set(plot_keys) != set(monthly)
    ):
        raise ValueError(
            "Local report hydrograph identities differ from the station-month quality inventory"
        )
    sections = [
        "<h1>FloodGuard · Local evidence review</h1>",
        (
            '<p class="notice"><strong>LOCAL RESEARCH ONLY — not a public redistribution artifact.</strong> '
            "Historical candidate evidence; no official warning or operational acceptance. Source reuse restrictions still apply. "
            "Confidence: low. Source periods vary by dataset; generated report time is not an observation timestamp.</p>"
        ),
        (
            f"<p>Source inventory: <code>{_escape(registry.get('source_inventory_sha256'))}</code><br>"
            f"Generated: {_escape(registry.get('generated_at'))} · {_escape(registry.get('verified_asset_count'))} verified source files.</p>"
        ),
        (
            '<nav><a href="#gauges">Water levels</a> · <a href="#facilities">Facility review</a> · '
            '<a href="#population">Population</a> · <a href="#terrain">Terrain</a> · <a href="#roads">Road evidence</a> · <a href="#layers">Local files</a></nav>'
        ),
        '<section id="gauges"><h2>Historical HII water levels</h2>',
        (
            f"<p>{len(series)} station-month plots from {_escape(gauges.get('stations'))} stations; "
            f"{_escape(gauges.get('rows'))} source rows, {_escape(gauges.get('numeric_slots'))} usable numeric slots, "
            f"{_escape(gauges.get('missing_measurement_rows'))} missing/null/sentinel source readings.</p>"
        ),
        (
            "<p>Units: metres above mean sea level, not flood depth. Observation timezone and source quality-flag meanings remain unconfirmed. "
            "No UTC conversion, interpolation, smoothing, missing-as-zero replacement or hydrological substitution. Numeric values remain scientifically unvalidated. "
            "Mae Sai September 2024 observations were not acquired; neighbouring rivers are not replacements.</p>"
        ),
        "<h3>Hat Yai: 20–28 November 2025 measurement coverage</h3>",
        _table(
            gauges.get("hat_yai_event_window", []),
            [
                ("station_code", "Station"),
                ("start_source", "Start"),
                ("end_source", "End"),
                ("numeric_slots", "Numeric slots"),
                ("missing_slots", "Missing slots"),
                ("expected_slots", "Expected slots"),
                ("measurement_coverage", "Measurement coverage"),
                ("event_peak_verified", "Event peak verified"),
            ],
        ),
        "<details><summary>All station-month quality checks</summary>",
        _table(
            station_months,
            [
                ("station_code", "Station"),
                ("month", "Source month"),
                ("numeric_slots", "Numeric"),
                ("missing_slots", "Missing"),
                ("absent_slots", "Absent timestamps"),
                ("duplicate_timestamp_rows", "Duplicate timestamps"),
                ("max_observed_m_msl", "Maximum observed (m MSL)"),
                ("aoi_matches", "AOI matches"),
            ],
        ),
        "</details>",
    ]
    for item in series:
        station, month = item["station_code"], item["month"]
        quality = monthly.get((station, month), {})
        coverage = [
            row
            for row in daily
            if row.get("station_code") == station
            and str(row.get("date_source", ""))
            .replace("-", "")
            .startswith(str(month).replace("-", ""))
        ]
        sections.extend(
            [
                (
                    f'<details class="hydrograph" data-station-month="{_escape(station)}-{_escape(month)}"><summary>{_escape(station)} · {_escape(month)} — '
                    f"{_escape(quality.get('numeric_slots'))} numeric / {_escape(quality.get('expected_slots'))} expected slots; "
                    f"{_escape(item.get('missing_slots'))} missing</summary>"
                ),
                _plot(item, plots.get("units", "m above MSL")),
                (
                    f'<p class="small">Source SHA-256: <code>{_escape(item.get("source_sha256"))}</code> · '
                    f"Confidence: {_escape(item.get('confidence', 'unvalidated_measurements'))} · source month {_escape(month)}.</p>"
                ),
                "<details><summary>Daily measurement coverage</summary>",
                _table(
                    coverage,
                    [
                        ("date_source", "Source date"),
                        ("numeric_slots", "Numeric slots"),
                        ("expected_slots", "Expected slots"),
                        ("measurement_coverage", "Measurement coverage"),
                        ("missing_measurement", "Missing measurements"),
                        ("absent_timestamp", "Absent timestamps"),
                    ],
                ),
                "</details></details>",
            ]
        )
    sections.extend(
        [
            '</section><section id="facilities"><h2>Shelter and healthcare identity review</h2>',
            (
                "<p>Source records are not verified sites. Shared coordinates remain unresolved; planned capacity is not available event capacity. "
                "Contact names and numbers are omitted. Search AOIs overlap and their counts must not be summed.</p>"
            ),
        ]
    )
    aoi_rows = [{"aoi": key, **value} for key, value in summary.get("aois", {}).items()]
    sections.append(
        _table(
            aoi_rows,
            [
                ("aoi", "Search AOI"),
                ("shelter_records", "Shelter source records"),
                ("shelter_distinct_coordinates", "Distinct coordinates"),
                ("healthcare_records", "2020 healthcare points"),
                ("event_accepted_shelter_capacity", "Accepted event capacity"),
            ],
        )
    )
    shelters = _csv(normalized / "shelter_records.csv")
    core = [
        row
        for row in shelters
        if any(
            str(aoi).startswith(("aoi-01", "aoi-03"))
            for aoi in _memberships(row.get("aoi_matches"))
        )
    ]
    facility_fields = [
        ("source_csv_record", "Source record"),
        ("place_name", "Place"),
        ("district", "District"),
        ("subdistrict", "Subdistrict"),
        ("village_community", "Village/community"),
        ("longitude", "Longitude"),
        ("latitude", "Latitude"),
        ("records_sharing_coordinate", "Records at this coordinate"),
        ("planning_capacity", "Unverified planned capacity"),
        ("site_identity_status", "Identity status"),
        ("record_id", "Traceable record ID"),
    ]
    sections.extend(
        [
            "<h3>Mae Sai and Hat Yai core identity crosswalk</h3>",
            _table(core, facility_fields),
            "<details><summary>All four-province shelter review records</summary>",
            _table(shelters, facility_fields),
            "</details>",
        ]
    )
    identity_review = _json(
        root / "facility_review" / "facility_identity_review.json", {}
    )
    if identity_review:
        sections.extend(
            [
                "<h3>Independent public-register identity checks</h3>",
                (
                    f"<p>{_escape(identity_review.get('supported_identity_matches'))} supported identity matches; "
                    f"{_escape(identity_review.get('unresolved_identities'))} unresolved. A current identity match does not establish event-time service, location accuracy or available capacity.</p>"
                ),
                _table(
                    identity_review.get("rows", []),
                    [
                        ("source_name", "Source place"),
                        ("kind", "Type"),
                        ("core_aois", "Core AOIs"),
                        ("identity_status", "Identity review"),
                        ("official_facility_id", "Official identifier"),
                        ("evidence_url", "Public evidence"),
                        ("coordinate_verified", "Coordinates verified"),
                        ("event_availability", "Event availability"),
                        ("review_note", "Review note"),
                    ],
                ),
            ]
        )
    healthcare = [
        row
        for row in _csv(normalized / "healthcare_records.csv")
        if _memberships(row.get("aoi_matches"))
    ]
    sections.extend(
        [
            "<details><summary>Healthcare candidates inside study AOIs</summary>",
            _table(
                healthcare,
                [
                    ("source_feature_index", "Original feature index"),
                    ("record_id", "Traceable ID"),
                    ("source_id_raw", "Nonunique source ID"),
                    ("longitude", "Longitude"),
                    ("latitude", "Latitude"),
                    ("aoi_matches", "AOIs"),
                    ("operation_status", "Operation status"),
                    ("event_availability", "Event availability"),
                ],
            ),
            "</details></section>",
        ]
    )
    population = datasets.get("population", {})
    sections.extend(
        [
            '<section id="population"><h2>Population context and denominators</h2>',
            (
                "<p>No observed subdistrict age allocation or 2024 Mae Sai age estimate is produced. 2023/2025 bracketing requires compatible definitions first; primary equity remains unavailable. "
                "Province/district shares are context, not measured local ages. Overlapping elderly groups are not summed.</p>"
            ),
            _table(
                population.get("sources", []),
                [
                    ("source_path", "Relative source"),
                    ("years_ce", "Reference years CE"),
                    ("geography_levels", "Geography"),
                    ("rows", "Rows"),
                    ("arithmetic_mismatches", "Sex-total mismatches"),
                ],
            ),
            "<h3>Mae Sai total versus compatible selected age categories</h3>",
            _table(
                population.get("mae_sai_comparisons", []),
                [
                    ("year_ce", "Year"),
                    ("age_category_sum", "Selected age-category sum"),
                    ("reported_population_total", "Reported district total"),
                    ("difference_total_minus_categories", "Unresolved difference"),
                    ("status", "Status"),
                ],
            ),
            "</section>",
            (
                '<section id="terrain"><h2>Terrain and flood-coverage quality review</h2><p>Historical DSM context only. Negative elevation is retained for review, not clamped to zero. '
                "Neither the surface model nor a gauge elevation establishes local inundation depth. Outside a flood analysis footprint is unobserved, not dry.</p>"
            ),
            _table(
                datasets.get("terrain", {}).get("rasters", []),
                [
                    ("aoi_id", "AOI"),
                    ("valid_pixels", "Valid pixels"),
                    ("negative_pixels", "Negative pixels"),
                    ("min_m", "Minimum m"),
                    ("max_m", "Maximum m"),
                    ("slope_p95_degrees", "95th percentile slope degrees"),
                    ("source_timestamp", "Source vintage"),
                ],
            ),
            _table(
                [
                    {"aoi": key, **value.get("flood_reference", {})}
                    for key, value in summary.get("aois", {}).items()
                ],
                [
                    ("aoi", "AOI"),
                    ("analysis_coverage_fraction", "Observed footprint fraction"),
                    ("unobserved_area_km2", "Unobserved km²"),
                    ("event_reference_accepted", "Event reference accepted"),
                ],
            ),
            "</section>",
            (
                '<section id="roads"><h2>Documentary road evidence</h2><p>No route is assumed open because a closure is absent. '
                "Report chainages and route/district conflicts require reconciliation; these records do not establish geocoded road closures.</p>"
            ),
            _table(
                _csv(normalized / "road_documentary_evidence.csv"),
                [
                    ("source_date", "Report date"),
                    ("highway", "Highway"),
                    ("segment_th", "Source segment"),
                    ("km_start", "From"),
                    ("km_end", "To"),
                    ("district_reported_th", "Reported district"),
                    ("traffic_status_original_th", "Original traffic phrase"),
                    ("quality_note", "Unresolved source issue"),
                    ("geometry_status", "Geocoding"),
                ],
            ),
            "</section>",
        ]
    )
    acquisition = _json(root / "acquisition" / "gap_register.json", {})
    drainage = _json(root / "acquisition" / "ngis" / "context_manifest.json", {})
    if acquisition or drainage:
        sections.extend(
            [
                "<section><h2>Additional acquisition checks and drainage context</h2>",
                "<p>Successful public access does not establish reuse rights or event-reference suitability. DWR streams and waterbodies are static context; source epoch, reuse terms and fine urban drainage completeness remain unresolved.</p>",
                _table(
                    acquisition.get("routes", []),
                    [
                        ("id", "Acquisition target"),
                        ("access", "Access result"),
                        ("usable_dataset_acquired", "Usable dataset acquired"),
                        ("suitability", "Suitability"),
                        ("fallback", "Fallback"),
                    ],
                ),
                _table(
                    drainage.get("records", []),
                    [
                        ("service", "DWR service"),
                        ("aoi_id", "AOI envelope"),
                        ("feature_count", "Source features"),
                        ("complete_response", "Complete response"),
                        ("source_epoch", "Source epoch"),
                        ("public_redistribution_accepted", "Redistribution accepted"),
                        ("assumptions", "Limits"),
                    ],
                ),
                "</section>",
            ]
        )
    sections.append(
        '<section id="layers"><h2>Normalized local files</h2><p>Open GeoJSON and GeoTIFF files in QGIS. These links remain inside the local research output; redistribution rights are separate.</p><ul>'
    )
    for path in sorted(normalized.glob("*")):
        if (
            path.is_file()
            and path.resolve().is_relative_to(normalized.resolve())
            and path.suffix.lower() in {".geojson", ".tif", ".csv", ".json"}
        ):
            sections.append(
                f'<li><a href="normalized/{html.escape(path.name, quote=True)}">{_escape(path.name)}</a></li>'
            )
    for directory in (root / "acquisition", root / "facility_review"):
        for path in sorted(directory.rglob("*")) if directory.exists() else []:
            if (
                path.is_file()
                and path.resolve().is_relative_to(root)
                and path.suffix.lower() in {".geojson", ".csv", ".json"}
            ):
                relative = path.relative_to(root).as_posix()
                sections.append(
                    f'<li><a href="{html.escape(relative, quote=True)}">{_escape(relative)}</a></li>'
                )
    sections.append("</ul></section>")
    style = (
        "body{font:14px/1.6 system-ui,sans-serif;color:#193d50;background:#f3f7f9;max-width:1300px;margin:30px auto;padding:0 24px}"
        "h1{font-size:32px}h2{font-size:23px}section{background:white;padding:24px;border:1px solid #cadce4;margin:24px 0;border-radius:8px}"
        ".notice{background:#fff1cb;padding:18px;border-left:4px solid #b58223}.empty{padding:16px;background:#eef3f6}"
        ".small,code{font-size:11px;overflow-wrap:anywhere}.table-scroll{overflow:auto}table{width:100%;border-collapse:collapse;font-size:11px}"
        "td,th{padding:9px;border:1px solid #cbdbe3;text-align:left;vertical-align:top;overflow-wrap:anywhere}th{background:#e4eff3}"
        "summary{cursor:pointer;padding:10px;font-weight:700}details{margin:14px 0;border:1px solid #d8e4e9;border-radius:5px}"
        "details>p,details>details{margin:12px}svg{width:100%;max-height:320px;background:#f7fafb}svg text{font:11px system-ui;fill:#34566a}"
        ".hydrograph>svg{display:block}a{color:#166a7e}nav{padding:14px 0}@media print{body{background:white;margin:0}section{break-before:page}details{break-inside:avoid}}"
    )
    document = (
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>FloodGuard local evidence review</title><style>'
        + style
        + "</style><body>"
        + "".join(sections)
        + "</body></html>"
    )
    root.mkdir(parents=True, exist_ok=True)
    destination = root / "local_evidence_report.html"
    destination.write_text(document, encoding="utf-8")
    return destination
