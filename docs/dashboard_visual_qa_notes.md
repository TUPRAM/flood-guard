# Historical Dashboard Visual QA Notes

Date: 2026-07-10

Scope: Dashboard v11 served from `outputs/dashboard.html` through a local static server.

Evidence status: historical snapshot for the dashboard build inspected on 2026-07-10. These screenshots were not regenerated after the active source lineage changed to the same-track original-SAFE pair and the current brief changed to `TH570903 / Ko Chang`; this file is therefore not current-release visual evidence.

Historical result: pass for fixture, Mae Sai weak-reference candidate, metadata/blocker, English/Thai, selected-area detail, and judge-presentation states in that inspected build. Screenshot evidence was saved outside Git; no screenshot files were committed.

## Environment

- Static server: `uv run python -m http.server 8124 -d outputs`
- Functional browser: Codex in-app browser
- Pixel captures: local headless Chrome
- Dataset used for viewport captures: `Mae Sai weak-reference candidate`
- Historical selected ADM3: `TH570906 / Wiang Phang Kham`
- Presentation state: judge mode with selected-area detail
- External evidence folder: `<external_data_workspace>/dashboard_qa/`
- Safety boundary checked: weak-reference, non-operational, not official validation, not field validated, and not an official warning

## Viewport Results

| Viewport | Result | Map and layout evidence |
| --- | --- | --- |
| `1440x900` | Pass | No horizontal overflow; map measured about `679x424` before judge-mode compaction; eight ADM3 labels rendered with zero overlaps; selected detail showed `984` road candidates and `5` typed facilities. Header, KPIs, warning, map, evidence, source quality, and the report-section start remained visible. |
| `1536x1024` | Pass | No horizontal overflow; map measured about `775x474` in the standard state and about `815x490` in judge mode; eight labels rendered with zero overlaps; `12-18` Leaflet tiles loaded during state changes. Warning, selected evidence, source quality, and report summaries remained visible. |
| `2048x1152` | Pass | No horizontal overflow; map measured about `1287x531`; eight labels rendered with zero overlaps; `18` Leaflet tiles loaded. Full map, source-quality panel, validation metrics, and action summary rendered without blank regions or clipping. |

The final Chrome captures contained clean FPPS symbols, no selected-unit popup obstruction, and distinct hospital, clinic, other healthcare, school, shelter, emergency-service, and community legend entries. Browser diagnostics contained no console errors or warnings.

## Semantic Map Results

- Regional Mae Sai view rendered `76` priority road candidates and `7` ADM3 facility clusters.
- Selecting `TH570906` forced zoom level `12` or closer and rendered `984` selected-area road candidates plus `5` individual facility markers.
- Current selected-area facility symbols included clinic, emergency service, school, and community candidates. Hospital and shelter symbols remain available for ADM3 units where those candidate types occur.
- The selected ADM3 retained full emphasis while neighboring ADM3 polygons remained visible at reduced emphasis.
- Language changes and responsive layout changes preserved selected-area detail instead of resetting to the regional extent.

## Interface Results

- English/Thai switching translated operational controls, dataset names, map status, evidence labels, legends, warnings, and Thai ADM3 names.
- Thai mode used the `Noto Sans Thai`, `Leelawadee UI`, Tahoma fallback stack and did not change identifiers or metric values.
- The Sentinel-1 evidence drawer showed the selected ADM3 pre/post acquisition dates, product ids, mean probability, P90 probability, binary share, and combined SAR change.
- Provenance used compact source-time, reference-status, and processing-scope cards; full product ids and assumptions remained expandable.
- Judge mode changed the left panel to `Dataset & Selection`, closed the redundant map popup, and hid scenario/export/context-library details.
- Judge mode retained the persistent warning, map, selected evidence, source quality, Sentinel-1 evidence, and compact provenance.

## Dataset Interaction Results

Fixture demo:

- Five fixture subdistrict choices rendered.
- Fixture road risk and scenario controls remained available.
- Validation report scope changed to `Fixture metrics`.

Mae Sai weak-reference candidate:

- Eight COD-AB ADM3 choices rendered.
- Priority polygons, semantically filtered candidate roads, clustered/typed candidate facilities, and modeled access hotspots were available.
- Selecting another ADM3 updated evidence, comparison, SAR statistics, map focus, and action summary.
- Provenance retained `weak_reference_candidate_cross_border_calibration`.

Metadata/blocker view:

- Scenario, road, facility, and access-hotspot controls were disabled.
- Action-brief and filtered-GeoJSON exports were disabled.
- Decision values were gated rather than represented as zero.
- Sentinel-1 evidence changed to `gated`.

## Remaining Evidence Limits

- The measurements and selected-area counts above apply only to the 2026-07-10 build. Run the current visual-QA matrix again before citing them for the active `TH570903 / Ko Chang` brief or current original-SAFE lineage.
- Mae Sai values are candidate outputs against a manually digitized cross-border weak reference, not official validation.
- OSM facilities are candidates and are not field verified.
- Road disruption and access hotspots are modeled, not observed incidents or closures.
- The dashboard remains static, non-operational, not real-time, and not an emergency warning.
