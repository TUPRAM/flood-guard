# Dashboard Demo QA Checklist

Use this checklist before a judge demo or recorded walkthrough. The dashboard is a static fixture-backed artifact: no backend, no build step, no browser-side `fetch`, no official warning claim, and no real flood-validation claim.

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
| `1440x900` | Laptop | Header, KPIs, controls, map, selected decision panel, and at least the top of reports |

## Manual Visual Checks

- The map fills the main workspace, not a thin strip.
- Subdistrict labels are readable and do not overlap at the starting zoom.
- The legend is inside the map area and does not float in blank space.
- The right panel defaults to `Action Brief` and shows `FG-TB-001 / River Market`.
- `Context Assets` says SAR, DEM, and THEOS-2 are context only.
- `Data Readiness` says processing remains gated.
- The `Read This First` narrative is visible in the controls panel and does not dominate the layout.
- The `Validation Summary` cards and `Action Brief` summary are visible below the map.

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
