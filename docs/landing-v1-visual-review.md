# FloodGuard landing v1 — visual review

Reviewed on 15 September 2026 in the local `codex/landing-v1-artwork` worktree. This report records agent visual review of the supplied artwork and actual browser captures. It does not claim human design approval, pixel equivalence, field performance, or deployment acceptance.

## Result

The implemented page preserves the supplied editorial direction: detailed neighborhood artwork, warm paper, dark geometric typography, restrained teal controls, the recurring resident and planner, and an analytical connection over the same place. The nine scenes remain readable across all six required viewport sizes. The final inspection found no remaining critical crop, route, card, label, portrait, or navigation collision in the settled scenes.

The last review found and corrected three defects that automated functional checks had not exposed: the resident's question crossing onto the map, the mobile observation label hiding its hollow pin, and a laptop card covering the start of the illustration caption. These corrections were recaptured and visually checked. The source reconciliation and smaller aesthetic differences are listed below.

## Review artifacts and scope

- [Side-by-side comparison gallery](../outputs/landing-v1-review/comparison.html): nine scene groups, each pairing the supplied desktop and mobile concept with the actual browser composition; links to the other four viewport captures.
- [Final capture manifest](../outputs/landing-v1-review/final/captures.json): 54 PNGs, nine scenes at six viewports.
- [Actual production hero](../outputs/landing-v1-review/production-hero.png): normal page with the skip link, manual motion control and retained PWA availability badge.
- [Native calibration outputs](../outputs/landing-v1-review/calibration/): W0/W1/W2 road registration captures, seed/proposed traces and native grid.
- [Execution record](landing-v1-execution.md) and [regression results](landing-v1-regression-results.md): implementation, tests, profiles, offline and CSP results.

All nine desktop references, all nine mobile references, the three native clean plates and the two transparent portraits were actually opened. The final acceptance pass opened every scene at every required viewport, with targeted rereads of the corrected regions after the final recapture. Review used the readable semantic regions, road alignment and visual hierarchy; no whole-image similarity percentage was treated as proof.

The 54 deterministic captures use the real shared components with review mode enabled and motion settled. They document composition, not actual scroll transitions. Normal-motion, reduced-motion, keyboard, no-JavaScript, enlarged-text and failure-path browser evidence is recorded separately under `docs/visual-qa/landing-v1/`. Browser acceptance and production export checks are separate from this visual judgment.

| Viewport | Capture suffix | Visual inspection |
|---|---|---|
| 1672 × 941 | `reference-desktop` | All nine scenes against the desktop source compositions |
| 1920 × 1080 | `desktop` | All nine; art scale, rail spacing, cards, endpoints and header |
| 1440 × 900 | `laptop` | All nine; long copy, card/clinic clearance, caption and question |
| 1024 × 768 | `tablet` | All nine; natural document flow, larger map and cards below it |
| 390 × 844 | `mobile` | All nine against mobile concepts; labels, hierarchy and local controls |
| 360 × 800 | `mobile-small` | All nine; narrow text wrapping, pin/label separation and controls |

Images show the complete scene element. Tablet and mobile images can be taller than the viewport; content is not squeezed into one screen.

## Capture, inspect and refine record

| Round | Recorded output | Main findings and correction |
|---|---|---|
| 1 | `outputs/landing-v1-review/round-1/` — 54 captures | Hero support was obscured by the town; finding card encroached on the clinic; long copy collided with portrait; mobile selection text was oversized; mobile crop extended beyond the image. |
| 2 | `outputs/landing-v1-review/round-2/` — 54 captures | Corrected hero scale/crop, compacted analytical card, reduced portrait footprint, fixed label sizing and constrained native crop. Further inspection identified a road trace leaving the pavement, hero clinic clipping and insufficient label separation. |
| 3 | `outputs/landing-v1-review/round-3/` — 54 captures | Recalibrated native route and affected span; separated observation and selection labels; widened hero mobile framing; moved repeated dry-endpoint qualification out of the small mobile map. |
| Final refinement | `outputs/landing-v1-review/final/` — refreshed 54 captures | Reduced 1100–1599px heading/body and analytical-card sizing; moved hero clinic label inward; placed desktop motion control inside the header; bounded the resident question to the rail; moved mobile observation label left/down; moved desktop caption clear of compact cards. Reopened the affected captures to verify each correction. |

The retained round count is evidence of actual iteration, not an aesthetic scoring system. The final folder supersedes earlier images, which intentionally retain visible defects from those rounds.

## Native artwork calibration

The clean artwork is the spatial authority. All plates, SVG geometry and projected DOM labels share one native 1536 × 1024 coordinate plane and crop transform.

- Household gate: `(453, 433)`; clinic entrance: `(1227, 629)`. Neither endpoint is placed on a roof.
- Replaced the proposed middle/clinic approach trace with a 17-point route following the visible W0/W1 pavement and clinic driveway. It passes through `(1098, 704)` before turning toward the clinic entrance.
- In W2, the affected segment is route indices 3–12, from `(532, 499)` to `(1098, 704)`. It follows the illustrated water-covered connection. Its broad span is intentional; it is not reduced to the seed marker's vicinity.
- Affected center: `(825, 610)`. The report pin is deliberately off the road at `(825, 703)` and remains an unverified sample.
- Homes label: `(410, 367)`; clinic label: `(1333, 718)`; hero clinic label: `(1333, 675)` to clear the lower edge.
- Observation label: `(750, 790)` with a mobile-only backing-box offset so its 44px control does not cover the hollow pin. Selection label: `(1030, 902)`; both remain separate from the route and caption in the final narrow captures.
- Desktop crop: `[0, 0, 1536, 1024]`; hero: `[0, 210, 1536, 510]`; stacked story crop: `[260, 190, 1250, 830]`; stacked hero crop: `[260, 120, 1250, 904]`.
- The dashed teal outline denotes a narrative selection. No arbitrary shoreline, simulated water rectangle, measured catchment, safe route or geographic claim was added.

The same W2 illustration and crop persist through S3A, observation, analysis, planning, public and ending. The ending keeps the water and the open questions.

## Per-scene outcome

| Scene | Final visual outcome |
|---|---|
| H-01 | Promise and both CTAs are immediately visible; W0 home/clinic remain identifiable; no portrait; clinic label clears the crop edge. |
| S1-01 | Resident and preparedness card; full gate-to-entrance blue connection; both dry endpoints visible. |
| S2-01 | W1 shows expanded water while the main road remains dry; card and long heading have separate readable space on laptops. |
| S3A-01 | Both dry-endpoint qualifications and amber affected span; resident question stays in its rail on desktop and follows the portrait in the narrow flow. |
| S3B-OBS | W2 plus hollow report pin, DEMO-R01 and Not verified. The narrow label no longer covers the pin. |
| S3B-01 | Planner, narrative selection and complete finding rows; card sits above the clinic on desktop and below the map in stacked flow. |
| S4-01 | Complete review brief, reason, next check and unknown clinic status; visible inspection control. |
| S4-PUBLIC | Resident and simpler household preparedness card; local story remains distinct from the real Public destination. |
| S4-END | No large portrait; W2 remains; planning/Public/evidence destinations and the brief remain readable. No visual all-clear. |

Transparent portraits retain their supplied tabletop and props, with no duplicate face, stretched body, floating torso or conspicuous halo on the selected paper. The prepared alpha planner asset contains fewer right-hand props than some composites; those missing composite props were not invented.

## Source reconciliation and remaining differences

1. **Canonical geography and scale.** The clean masters depict a broader, softer neighborhood than several full-page and separately generated mobile composites. The implementation keeps one canonical world and responsive crop. Its mobile map has smaller buildings and more visible surrounding land; its hero framing is closer to the clean master than the composite's differently placed river and roofs. Stretching or replacing the master to chase those compositions would break registration.
2. **Typography and spacing.** The existing locally bundled Inter is used. Its glyph shape, weight and line breaks differ from the raster references. Long headings reflow, card type is smaller on laptops, and mobile content uses its natural height. The ending uses the standard story title scale, keeping it a concise conclusion. The active chapter navigation adds real previous/next and an accessible narrow-screen chapter menu.
3. **Paper and art edge.** The page uses `#faf8f2`, close to the actual clean plate background; the written token was `#f3f1e8`. The artwork retains its native tone. A faint rectangular edge is still perceptible in some W1/W2 desktop scenes, and the hero uses a soft upper-edge blend. These are minor tonal differences; the town is not globally faded or tinted.
4. **Analytical presentation.** Route lines and labels are intentionally clean, readable browser elements. They lack some glow, pointer tails and decorative shoreline tracing in the concepts. Mobile dry-endpoint qualification is a single line below the map, keeping the two buildings clear. The closing state retains the inspectable brief and unverified sample from the authoritative story data, so it is more explicit than the abbreviated closing concept.
5. **Artwork resolution.** Plates are natively 1536px wide. Detail is visibly softer when enlarged to the wide hero or on high-DPR displays. No interpolated 4K artwork or newly generated town was substituted. This is a source-resolution limit, not a claim of native high-DPR rendering.
6. **Preserved application chrome.** The production page includes the existing PWA availability badge and skip link, which are absent from the storyboard images. The inspected production hero shows the badge near the clinic label's lower-right border; the label text, clinic and entrance remain readable. Review-mode captures omit this global availability badge and should not be mistaken for a complete production shell.

These differences do not prevent reading the narrative or using its controls. Owner design acceptance remains separate from this agent review.

## Production and fallback visual notes

The actual production hero was opened after the settled review captures. Its text, labels, artwork and header agree with the reviewed layout; the normal-motion control reads “Reduce motion,” and the saved-app availability badge remains visible.

A later production no-JavaScript capture exposed the browser's broken-image outline on an intentionally source-less deferred portrait placeholder. The implementation now hides `img:not([src])` within the landing only, retaining its dimensions and the real `<noscript>` image. Loaded artwork and the settled 54 compositions are unchanged. The production browser suite owns the rebuilt no-JavaScript verification and capture; see the regression record for the exact final result.

## Reproduce the composition review locally

From the implementation worktree, run the development server with `NEXT_PUBLIC_FLOODGUARD_LANDING_REVIEW=1`, then:

```powershell
node handoff/floodguard-landing-v1/tools/capture-review.mjs --repo . --url http://127.0.0.1:3100/ --out outputs/landing-v1-review/final
```

The gallery uses local relative links to supplied references and final browser images; open `outputs/landing-v1-review/comparison.html` locally. Review-mode capture requires the explicit build flag. Normal production exports keep the gate off. Nothing was pushed or deployed for this review.
