# Proposal-stage responsive visual QA

These six captures are generated from the production static export with the
FastAPI service unavailable. They document layout and offline behavior only;
they do not represent current flood conditions or operational readiness.

| Viewport | Route/state | Evidence file |
|---|---|---|
| 390 x 844 | `/public` home, Thai | `public-390x844.png` |
| 430 x 932 | `/public` map, Thai | `public-map-430x932.png` |
| 1024 x 768 | `/command`, temporary-shelter scenario and persistent evidence drawer, English | `command-1024x768.png` |
| 1440 x 900 | `/command`, temporary-shelter scenario comparison, English | `command-1440x900.png` |
| 1536 x 1024 | `/command`, temporary-shelter scenario comparison, English | `command-1536x1024.png` |
| 2048 x 1152 | `/studio`, English | `studio-2048x1152.png` |

The capture task also checks horizontal overflow, map-control clipping,
visible keyboard focus, Thai rendering, source/confidence/status disclosures,
unsupported live wording, and external requests. It also asserts that the
public action/help hierarchy starts in the first viewport, the public map has a
selected-area sheet, the 1024 x 768 drawer is not clipped, and command map and
evidence state use the same server-produced scenario. The map geometry and
context are synthetic fixtures and are visibly labelled as unverified and not
administrative boundaries.

## Comparison with the previous reviewed capture set

The regenerated PNGs were compared pixel-for-pixel with the files at source
commit `8a9ddfc6f4094feec043856241bf8f30e113bfcd`. All dimensions are unchanged;
the differences are intentional layout/state changes and every new image was
also visually inspected.

| Capture | Pixels changed | Visual review |
|---|---:|---|
| `public-390x844.png` | 66.21% | Pass: household-plan action and official help establish the first-viewport hierarchy |
| `public-map-430x932.png` | 56.31% | Pass: context, full legend, selected-area sheet, and limitation notice remain readable |
| `command-1024x768.png` | 37.25% | Pass: two-column workspace and persistent evidence drawer fit without clipping |
| `command-1440x900.png` | 40.72% | Pass: scenario fill, legend, ranking, and right evidence panel agree |
| `command-1536x1024.png` | 35.21% | Pass: dense command layout remains legible with provenance and controls |
| `studio-2048x1152.png` | 64.10% | Pass: integration, qualified-evaluation, and decision-eligibility scopes are distinct above the fold |

Regenerate after a successful static build:

```powershell
Set-Location apps/web
pnpm qa:visual
```
