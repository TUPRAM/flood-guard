# Dashboard Visual QA Notes

Date: 2026-07-08

Scope: `outputs/dashboard.html` served from `http://127.0.0.1:8000/dashboard.html`.

Status: pass for the fixture-backed judge-demo dashboard. No screenshot files were saved or committed.

## Environment

- Static server: `uv run python -m http.server 8000 -d outputs`
- Browser path: Codex in-app browser
- Dashboard source: committed generated `outputs/dashboard.html`
- Safety boundary checked: fixture-backed, non-operational, not an official warning, context only, processing remains gated

## Viewport Results

| Viewport | Result | Notes |
| --- | --- | --- |
| `1536x1024` | Pass | Header, KPI strip, controls, map, decision panel, validation cards, and action-brief summary were visible. Map measured about `799x479`; 5 subdistrict labels rendered with no overlaps; 8 map tiles loaded; 8 interactive map shapes rendered; no console warnings/errors. |
| `2048x1152` | Pass | Same first-viewport content remained visible. Map measured about `1327x479`; 5 subdistrict labels rendered with no overlaps; 12 map tiles loaded; 8 interactive map shapes rendered; no large blank map whitespace; no console warnings/errors. |
| `1440x900` | Pass | Laptop viewport still showed header, KPI strip, controls, map, decision panel, validation cards, and action-brief summary start. Map measured about `703x449`; 5 subdistrict labels rendered with no overlaps; 8 map tiles loaded; 8 interactive map shapes rendered; no console warnings/errors. |

## Interaction Results

- Subdistrict selection: selecting `FG-TB-002 / Bridge Junction` updated the visible KPI state.
- Visible readback for `FG-TB-002`:
  - FPPS: `63.85`
  - Action class: `B`
  - Confidence: `medium`
  - Baseline 30-minute access loss: `30`
  - Equity gap ratio: `5.999`
  - Temporary shelter delta: `-30`
  - Road closure delta: `+50`
- Scenario selector:
  - `temporary shelter delta` selected successfully.
  - `road closure delta` selected successfully.
- Action-class filter:
  - Unchecking `A` reduced labels from 5 to 4 and interactive map shapes from 8 to 7.
  - Rechecking `A` restored labels to 5 and interactive map shapes to 8.
- Export buttons:
  - `Download current brief` and `Download filtered GeoJSON` were visible, enabled, and clickable.
  - The in-app browser did not expose a download event for the Blob download during QA. Clicking did not produce console warnings/errors.

## Rehearsal Notes

- The 3-5 minute path works best when starting with `FG-TB-001 / River Market`, then switching to `FG-TB-002 / Bridge Junction` for scenario contrast.
- The clearest spoken line is: "FloodGuard ranks local action priorities from flood, exposure, access, equity, and road-risk evidence."
- Use `FG-TB-002` to explain policy action:
  - temporary shelter: fewer people lose 30-minute access
  - road closure: more people lose 30-minute access
- Keep SAR, DEM, and THEOS-2 language strict: context only, not flood labels, not validation, not official warning evidence.

## Current Blockers

- UNOSAT/UNITAR and GISTDA provider responses are still pending in the repository logs.
- Real Mae Sai validation remains blocked because no legal reference mask, local file paths, SHA-256 checksums, and cleared file-level manifest rows exist yet.
- Real-data ML remains blocked until legal labels and a real non-ML SAR baseline exist.
