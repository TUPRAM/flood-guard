# Dashboard Visual QA Notes

Date: 2026-07-10

Scope: Dashboard v10 served from `outputs/dashboard.html` through a local static server.

Status: pass for fixture, Mae Sai weak-reference candidate, and metadata/blocker modes. Screenshot evidence was saved outside Git; no screenshot files were committed.

## Environment

- Static server: `uv run python -m http.server 8123 -d outputs`
- Browser path: Codex in-app browser
- Dataset used for viewport captures: `Mae Sai weak-reference candidate`
- Windows display scaling produced CSS viewports smaller than the requested screenshot pixel dimensions; both the requested screenshot size and measured CSS viewport are recorded below.
- Safety boundary checked: weak-reference, non-operational, not official validation, not field validated, and not an official warning

## Viewport Results

| Screenshot target | Measured CSS viewport | Result | Map and layout evidence |
| --- | --- | --- | --- |
| `1440x900` | `1200x750` | Pass | Three-column workspace remained visible. Map measured about `519x420`; eight ADM3 labels rendered with zero overlaps; 15 map tiles loaded; warning and structured evidence remained visible; no horizontal overflow. Reports remain directly below the main workspace. |
| `1536x1024` | `1280x853` | Pass | Map measured about `522x420`; eight ADM3 labels rendered with zero overlaps; 15 map tiles loaded; warning, decision evidence, and the start of the report section were visible; no horizontal overflow. |
| `2048x1152` | `1706x960` | Pass | Map measured about `949x540`; eight ADM3 labels rendered with zero overlaps; 18 map tiles loaded; warning, evidence, source quality, and report panels were visible; no horizontal overflow or blank map region. |

Every capture contained a Leaflet vector canvas, loaded map tiles, zero open popups, and the candidate facility/access-hotspot controls. Browser diagnostics contained no console errors or warnings.

## Dataset Interaction Results

Fixture demo:

- Five fixture subdistrict choices rendered.
- Fixture road risk remained available.
- Temporary-shelter and road-closure scenario controls remained enabled.
- Validation report scope changed to `Fixture metrics`.

Mae Sai weak-reference candidate:

- Eight COD-AB ADM3 choices rendered.
- Priority polygons, candidate road risk, candidate OSM facilities, and modeled access hotspots were available.
- Selecting `TH570903 / Ko Chang` updated the selected-unit comparison to the modeled maximum 30-minute access loss of `190` people.
- The report scope changed to `Weak-reference candidate metrics`.
- Provenance retained `weak_reference_candidate_cross_border_calibration`.

Metadata/blocker view:

- Scenario, road, facility, and access-hotspot controls were disabled.
- Action-brief and filtered-GeoJSON exports were disabled.
- Decision values were gated rather than represented as zero.
- Report scope changed to `Processing gates`.

## Visual Findings

- A Windows-scaled `1440x900` frame initially triggered the two-column tablet breakpoint. The breakpoint was lowered so the approved three-zone layout now remains intact.
- The `TH570901` and `TH570906` labels initially collided at the widest map. Small deterministic label offsets now keep all eight labels separate at every required viewport.
- The weak-reference warning remains directly below the KPI strip in every dataset mode.
- The structured evidence panel keeps FPPS, flood evidence, expected exposure, modeled access loss, proxy equity, road evidence, terrain coverage, comparison, source quality, and provenance separate.
- Raw source paths do not appear in the page. Map layers contain only committed derived GeoJSON and embedded context metadata.

## Remaining Evidence Limits

- Mae Sai values are candidate outputs against a manually digitized cross-border weak reference, not official validation.
- OSM facilities are candidates and are not field verified.
- Road disruption and access hotspots are modeled, not observed incidents or closures.
- The dashboard remains static, non-operational, not real-time, and not an emergency warning.
