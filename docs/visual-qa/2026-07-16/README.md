# Responsive visual QA — 2026-07-16

These renders are generated from the local offline judging application. The
browser matrix is intentionally role-specific:

| Viewport | Route | Evidence file |
| --- | --- | --- |
| 390 x 844 | `/public` home | `public-390x844.png` |
| 430 x 932 | `/public` map | `public-map-430x932.png` |
| 1024 x 768 | `/command` | `command-1024x768.png` |
| 1440 x 900 | `/command` | `command-1440x900.png` |
| 1536 x 1024 | `/command` | `command-1536x1024.png` |
| 2048 x 1152 | `/studio` | `studio-2048x1152.png` |

The corresponding automated checks cover route content, Next.js error overlays,
horizontal overflow, source-time/confidence disclosures, same-origin resources,
keyboard focus, and service-worker-backed offline reloads. Screenshots are
evidence of rendering only; they are not evidence of current flood conditions.

Regenerate the six captures after a successful production build:

```powershell
pnpm qa:visual
```
