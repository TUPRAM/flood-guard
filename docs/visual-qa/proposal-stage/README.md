# Proposal-stage responsive visual QA

These six captures are generated from the production static export with the
FastAPI service unavailable. They document layout and offline behavior only;
they do not represent current flood conditions or operational readiness.

| Viewport | Route/state | Evidence file |
|---|---|---|
| 390 x 844 | `/public` home, Thai | `public-390x844.png` |
| 430 x 932 | `/public` map, Thai | `public-map-430x932.png` |
| 1024 x 768 | `/command`, English | `command-1024x768.png` |
| 1440 x 900 | `/command`, English | `command-1440x900.png` |
| 1536 x 1024 | `/command`, English | `command-1536x1024.png` |
| 2048 x 1152 | `/studio`, English | `studio-2048x1152.png` |

The capture task also checks horizontal overflow, map-control clipping,
visible keyboard focus, Thai rendering, source/confidence/status disclosures,
unsupported live wording, and external requests. The map geometry is a
synthetic fixture and is visibly labelled as not being an administrative
boundary.

Regenerate after a successful static build:

```powershell
Set-Location apps/web
pnpm qa:visual
```
