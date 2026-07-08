from __future__ import annotations

from pathlib import Path

from floodguard.dashboard import write_static_dashboard

OUTPUTS = Path(__file__).parents[1] / "outputs"


def test_write_static_dashboard_embeds_outputs_without_backend_fetch(tmp_path: Path) -> None:
    output_path = tmp_path / "dashboard.html"

    written = write_static_dashboard(
        OUTPUTS / "priority_subdistricts.geojson",
        OUTPUTS / "road_risk.geojson",
        OUTPUTS / "validation_summary.md",
        [
            OUTPUTS / "action_brief_FG-TB-001.md",
            OUTPUTS / "action_brief_FG-TB-002.md",
            OUTPUTS / "action_brief_FG-TB-003.md",
        ],
        output_path,
        theos2_preview_manifest_path=OUTPUTS / "theos2_selected_file_manifest.csv",
    )

    html = output_path.read_text(encoding="utf-8")
    assert written == output_path
    assert "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" in html
    assert "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" in html
    assert "const priorityData =" in html
    assert "const roadRiskData =" in html
    assert "const briefsBySubdistrict =" in html
    assert "const theos2PreviewData =" in html
    assert "const sentinel1QuicklookData =" in html
    assert "const demQuicklookData =" in html
    assert "const localDataLibrarySummary =" in html
    assert 'class="app-header"' in html
    assert 'data-dashboard-section="app-header"' in html
    assert 'class="kpi-strip"' in html
    assert 'data-dashboard-section="kpi-strip"' in html
    assert 'class="dashboard-workspace"' in html
    assert 'data-dashboard-section="dashboard-workspace"' in html
    assert 'class="control-panel"' in html
    assert 'class="map-panel"' in html
    assert 'data-dashboard-section="map-panel"' in html
    assert 'class="decision-panel"' in html
    assert 'data-dashboard-section="decision-panel"' in html
    assert 'data-dashboard-section="context-readiness-panel"' in html
    assert 'data-dashboard-section="report-section"' in html
    assert "Fixture demo" in html
    assert "Non-operational" in html
    assert "Real validation blocked" in html
    assert "Static HTML | embedded data | no backend" in html
    assert "Priority Map" in html
    assert "map.invalidateSize" in html
    assert "const mapBoundsPadding = 0.16" in html
    assert "function fitPriorityMapToData" in html
    assert "function settleMapLayout" in html
    assert "bounds.pad(mapBoundsPadding)" in html
    assert "ResizeObserver" in html
    assert "bounds.pad(0.18)" not in html
    assert "subdistrict-label" in html
    assert "layer.bindTooltip" in html
    assert "escapeHtml(id)" in html
    assert "width: 74px" in html
    assert "minmax(540px, 1fr)" in html
    assert "height: clamp(500px, calc(100vh - 390px), 540px)" in html
    assert "Controls &amp; Scenario" in html
    assert "Context only. Not flood detection. Not validation. Not an official warning." in html
    assert 'class="context-preview-grid"' in html
    assert 'class="app-footer"' in html
    assert 'data-dashboard-section="app-footer"' in html
    assert "Generated: 2025-07-07 08:00 ICT" in html
    assert 'class="validation-metric-grid"' in html
    assert 'class="validation-metric"' in html
    assert "Toy metrics are synthetic fixtures only" in html
    assert "F1 / Dice" in html
    assert "0.67" in html
    assert 'class="brief-summary"' in html
    assert "Data Readiness" in html
    assert "Read This First" in html
    assert "Fixture-backed decision demo" in html
    assert "Real Mae Sai validation is blocked" in html
    assert "provider response pending" in html
    assert "Context layers are not flood labels" in html
    assert "Real-data ML is not allowed" in html
    assert "Sentinel-1 SAR Context" in html
    assert 'id="sentinel1-sar-context"' in html
    assert "sentinel1_quicklook_vv.png" in html
    assert "sentinel1_quicklook_vh.png" in html
    assert "SAR context only" in html
    assert "not flood detection" in html
    assert "not validation" in html
    assert "not an official warning" in html
    assert "event timing unresolved unless proven otherwise" in html
    assert "DEM Terrain Context" in html
    assert 'id="dem-terrain-context"' in html
    assert "dem_quicklook.png" in html
    assert "DEM terrain quicklook" in html
    assert "DEM terrain context only" in html
    assert "not flood observation" in html
    assert "not flood label" in html
    assert "not reference mask" in html
    assert "not an official warning" in html
    assert "THEOS-2 Optical Context" in html
    assert "Optical context only; not flood validation or an official warning." in html
    assert "theos2_previews/theos2_preview_" in html
    assert "Local Data Library" in html
    assert 'id="local-data-library"' in html
    assert "sentinel1_sar" in html
    assert "copernicus_dem" in html
    assert "theos2_optical" in html
    assert "Local Sentinel-1 readiness" in html
    assert "Sentinel-1 provenance status" in html
    assert "timing_unresolved" in html
    assert "SAR quicklooks: 2" in html
    assert "DEM readiness" in html
    assert "DEM quicklooks: 1" in html
    assert "terrain context only" in html
    assert "THEOS-2 optical context readiness" in html
    assert "optical context only" in html
    assert "Source files are outside Git and processing remains gated." in html
    assert "local_data_library_manifest.csv" in html
    assert "sentinel1_selected_file_manifest.csv" in html
    assert "sentinel1_provenance_resolved_manifest.csv" in html
    assert "sentinel1_quicklook_manifest.csv" in html
    assert "dem_selected_file_manifest.csv" in html
    assert "dem_quicklook_manifest.csv" in html
    assert "C:\\Users" not in html
    assert "C:/Users" not in html
    assert "official flood observations" not in html
    assert 'id="subdistrict-select"' in html
    assert 'id="scenario-select"' in html
    assert 'id="dataset-mode-select"' in html
    assert "fixture demo" in html
    assert "public-data Mae Sai candidate" in html
    assert "blocked/metadata-only view" in html
    assert "const datasetModeNotes =" in html
    assert "Public-data Mae Sai candidate: Sentinel Asia / MBRSC geometry QA found 514 Mae Sai review-bbox features" in html
    assert "CDSE pre/post Sentinel-1 rows are selected" in html
    assert "Blocked/metadata-only view: source candidates are documented" in html
    assert "dataset-mode-note" in html
    assert 'class="action-filter"' in html
    assert "temporary shelter delta" in html
    assert "road closure delta" in html
    assert "Best intervention effect" in html
    assert "Worst road-closure stress case" in html
    assert "Temporary shelter: -30 people losing 30-min access" in html
    assert "Road closure: +50 people losing 30-min access" in html
    assert 'id="download-current-brief"' in html
    assert 'id="download-filtered-geojson"' in html
    assert "Download current brief" in html
    assert "Download filtered GeoJSON" in html
    assert "function downloadCurrentActionBrief" in html
    assert "function downloadFilteredGeoJSON" in html
    assert "function downloadText" in html
    assert "new Blob" in html
    assert "priority_subdistricts_filtered.geojson" in html
    assert "Delta improves" in html
    assert "Delta worsens" in html
    assert "Action Brief" in html
    assert "Validation Summary" in html
    assert "A Protect Lives" in html
    assert "action_brief_FG-TB-001" not in html
    assert "FG-TB-001" in html
    assert "FG-TB-002" in html
    assert "FG-TB-003" in html
    assert "temporary_shelter_change_people_losing_30_min_access" in html
    assert "road_closure_change_people_losing_30_min_access" in html
    assert "function selectSubdistrict" in html
    assert "function renderPriorityLayer" in html
    assert "fetch(" not in html


def test_write_static_dashboard_can_render_true_thumbnail_cards(tmp_path: Path) -> None:
    thumbnail_manifest = tmp_path / "theos2_thumbnail_manifest.csv"
    thumbnail_manifest.write_text(
        "\n".join(
            [
                "file_name,source_timestamp,category,sha256,thumbnail_path,thumbnail_format,raster_reader",
                "IMG_T2V_20250730033331_ORTHO_PMS_32-004.tif,2025-07-30T03:33:31Z,Disaster,"
                "aaaaaaaaaaaa,theos2_thumbnails/theos2_thumbnail_004.png,png,rasterio",
            ]
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "dashboard.html"

    write_static_dashboard(
        OUTPUTS / "priority_subdistricts.geojson",
        OUTPUTS / "road_risk.geojson",
        OUTPUTS / "validation_summary.md",
        OUTPUTS / "action_brief_FG-TB-001.md",
        output_path,
        theos2_preview_manifest_path=thumbnail_manifest,
    )

    html = output_path.read_text(encoding="utf-8")
    assert "theos2_thumbnails/theos2_thumbnail_004.png" in html
    assert "True PNG thumbnail via rasterio" in html
    assert "Metadata SVG preview card" not in html
    assert "not flood validation or an official warning" in html


def test_dashboard_output_contract_path() -> None:
    assert (OUTPUTS / "dashboard.html").as_posix().endswith("outputs/dashboard.html")
