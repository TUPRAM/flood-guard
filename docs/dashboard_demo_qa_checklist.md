# Dashboard Demo QA Checklist

Use this checklist before a judge demo or recorded walkthrough. The dashboard is a static artifact with a fixture dataset and a Mae Sai weak-reference candidate dataset: no backend, no build step, no browser-side `fetch`, no official warning claim, and no official flood-validation claim.

## Regenerate And Smoke Check

Run from the repository root:

```powershell
cd "C:\Users\iputu\Documents\Flood Guard"
uv run pytest
uv run python scripts/generate_sample_priority.py
uv run python scripts/generate_sample_decision_outputs.py
uv run python scripts/smoke_dashboard.py
```

Optional network tile probe before a live demo:

```powershell
uv run python scripts/smoke_dashboard.py --check-network-tiles
```

The smoke check must report pass/fail for:

- page title and app identity
- local static-server fetch
- Leaflet and OpenStreetMap tile configuration
- embedded priority polygons and road-risk segments
- embedded Mae Sai ADM3 polygons, candidate facilities, and modeled access hotspots
- full dataset switching between fixture, Mae Sai candidate, and blocker modes
- subdistrict label overlap guards
- validation cards and action brief summary
- export buttons
- no browser-side `fetch`
- no absolute local source paths

## Start The Local Server

Direct file opening works for the current dashboard:

```powershell
start outputs\dashboard.html
```

For the most reliable judge setup, serve the `outputs/` folder:

```powershell
uv run python -m http.server 8000 -d outputs
```

Open:

```text
http://localhost:8000/dashboard.html
```

## Required Viewports

Capture or inspect these exact browser sizes:

| Viewport | Purpose | Must show in first viewport |
| --- | --- | --- |
| `1536x1024` | Judge frame | Header, KPI strip, controls, map, decision panel, validation/action summary start |
| `2048x1152` | Large monitor | Same content with no label collision and no large blank map area |
| `1440x900` | Laptop | Header, KPIs, persistent warning, controls, map, and selected decision panel; reports remain immediately below the workspace |

## Manual Visual Checks

- The map fills the main workspace, not a thin strip.
- Subdistrict labels are readable and do not overlap at the starting zoom.
- The legend is inside the map area and does not float in blank space.
- The right panel defaults to structured evidence for the selected unit and shows the active dataset's decision status.
- The weak-reference or blocker warning remains visible directly below the KPI strip after switching modes.
- `Context Assets` says SAR, DEM, and THEOS-2 are context only.
- `Data Readiness` says processing remains gated.
- The compact evidence-boundary narrative is visible in the controls panel and does not dominate the layout.
- The `Validation Summary` cards and `Action Brief` summary are reachable immediately below the main workspace.

## Interaction Checks

1. Select `FG-TB-002 / Bridge Junction`.
2. Confirm KPI cards and right-panel values update.
3. Switch scenario mode to `temporary shelter delta`.
4. Confirm improvement styling and the temporary-shelter delta remain visible.
5. Switch scenario mode to `road closure delta`.
6. Confirm worsening styling and road-closure delta remain visible.
7. Uncheck action class `A`, then recheck it.
8. Click `Download current brief`.
9. Click `Download filtered GeoJSON`.
10. Switch dataset mode to `Mae Sai weak-reference candidate`.
11. Confirm exactly eight ADM3 choices, candidate road/facility/hotspot toggles, structured evidence, source quality, and provenance.
12. Select a second Mae Sai subdistrict and confirm evidence, comparison, map focus, and action summary update.
13. Switch to `Metadata/blocker view` and confirm decision values and unavailable layers are gated rather than shown as zeros.
14. Switch back to `Fixture demo` and confirm scenario controls and fixture geometry return.

## Required Wording

The page must still say:

- fixture-backed
- non-operational
- not an official warning
- context only
- not flood detection
- not validation
- real validation blocked
- source files are outside Git
- processing remains gated

## Do Not Stage Source Data

Before committing, confirm no raw source data is staged:

```powershell
git diff --cached --name-only | rg -i "\.(tif|tiff|zip|safe|jp2|ovr|nc|grib|h5|hdf)$"
```

The command should print nothing.
