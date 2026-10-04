# Connected Terrain Landing Page

The current desktop revision is documented in
[Desktop V3: One Continuous Aerial World](landing-desktop-v3.md). The V2 design
and verification below describe the preserved mobile/static artwork and the
previous desktop direction; they are not the acceptance record for V3.

Implemented from the supplied FloodGuard production blueprint, English content
contract, and review wireframe. These materials define design intent; they do not
authorize operational integration, deployment, or a claim of agency acceptance.
The implementation starts from upstream commit
`28922691839593193aee10ad31feb22abcfbe0dc`.

## Scope and Design

The competition entry is a complete English landing page with immediate Public,
Planning and Studio links, eight semantic story chapters, a method diagram, dated
Mae Sai source context, three workspace entries, FAQs and source disclosures.
FloodGuard is the H1 and first-viewport brand; the supplied two-line headline is
retained immediately beneath it. The Public production entry is unchanged.
The opening shares one visual stage with the story. The first-viewport cue links
to the actual `place` chapter, while workspace entry remains immediate.

The second visual direction was explicitly authorized on 9 September 2026.
Its sequence is `place`, `dry`, `flood`, `access`, `public`, `command`, `studio`,
and `shared`. One original architectural district supplies every modeled state.
The dry, flooded and interrupted-connection views hold the same camera. The
closing overview retains the water: the product changes understanding and
coordination, not the physical flood.

The story records are fictional. The example receipt and ordered workflow are
labeled separately from the active presentation status. Receipt, review,
assignment and acknowledgment remain distinct. Scrolling never submits a report,
requests location, contacts a service, changes a task, or publishes a model.
Case metadata comes from the committed historical manifest; no new analytical
metric is inferred from the illustration. The optical context image is dated
February 2024 and is explicitly not a September flood mask.

The full static article is exported as HTML. At eligible desktop sizes, one
orthographic R3F canvas enhances it using a measured GSAP clock. Native scroll,
deep links, reverse seeking, browser preferences and a locally persisted motion
control remain available. Reduced motion, compact screens, data-saving mode,
unsupported graphics, failed downloads, lost contexts and sustained slow rendering
retain the illustrated article. An explicit mode switch preserves the reading
position. Rendering stops when settled, hidden or outside the visible story.

## Original Art

The editable master is
`apps/web/src/components/landing/scene/terrain-scene.ts`, with authored geometry,
materials, scale figures, lighting and four stable visual anchors.
The same master generates both live scene frames and responsive WebP stills.
The GLB export provides a portable art handoff; the runtime does not
download it or need decoder workers. The source and asset manifest document
provenance, dimensions, sizes and SHA-256 hashes.

This implementation uses editable procedural Three.js source instead of a
Blender project. The supplied package contained commissioning specifications,
not finished artwork. No Illoca artwork, models, proprietary fonts or animation
clips were reused. The supplied photo-style aerial is used only as an explicitly
labelled Mae Sai-inspired concept. Its geography is unverified. The selected
region and inferred architectural district are not a georeferenced or
photogrammetric reconstruction. The separate flood photograph is not presented
as a documentary before-and-after match. Inundation and network interruption
are illustrative, not measured depths, a forecast or a verified closure.
Native Thai localization, external art direction signoff, audience comprehension
testing and agency acceptance are not represented as completed.

## Profiles and Cache

Next.js resolves `@floodguard/root-entry` to the appropriate profile component
before compilation. This prevents an unused landing client dependency from
entering a Public-only build. Both Turbopack and Webpack resolve the same profile;
TypeScript checks the competition entry's common export.

Static export, trailing slashes and unoptimized Next images are preserved.
`write-offline-assets.mjs` excludes the optional renderer from the competition
precache while retaining any dependency referenced directly by shipped HTML.
Public builds prune the landing art and assert that no landing code enters the
mandatory offline inventory. No CSP relaxation was added.

Fast Public-to-landing navigation exposed an existing Leaflet 1.9.4 Canvas race:
a synchronous redraw clears the saved animation-frame handle without cancelling
the previously queued callback. Renderer teardown can then cancel only the newer
handle. An initial path-removal ordering workaround did not eliminate the race
and was removed. Each map now owns a Canvas subclass whose public add/remove
lifecycle guards the one version-pinned `_redraw` override. An orphaned callback
cannot touch a removed context; no global Leaflet prototype is changed. Native
map teardown and the existing SVG fallback remain intact. Focused tests reproduce
the lost-handle sequence and verify independent maps and reattachment. Browser
verification repeats eight Public-to-landing cycles with varying short delays.

Social image metadata uses the actual Vercel deployment hostname when available.
Without that build context, only title and description are emitted; a local build
does not publish a broken localhost or unrelated-production image URL.

## Reproduce

From the repository root:

```powershell
pnpm install --frozen-lockfile
pnpm --filter @floodguard/web art:landing --context-image "<path to the supplied illustrative aerial>"
pnpm lint
pnpm typecheck
pnpm test:web
pnpm test:contracts
pnpm --filter @floodguard/web verify:profiles
pnpm --filter @floodguard/web qa:landing
pnpm test:offline
pnpm test:csp
pnpm --filter @floodguard/web dev --hostname 127.0.0.1 --port 4310
```

The landing QA command starts and closes its own local gzip-enabled static
server and Chromium browser. It records browser, platform, viewport, transfer,
rendering, accessibility and screenshot evidence in
`apps/web/test-results/landing-v2/landing-smoke.json`. It checks the exported HTML
with the repository's production security headers. Its service worker is blocked
to isolate page transfer measurements; separate profile and offline tests exercise
the real service worker.

Art regeneration requires the source aerial explicitly. Use the supplied
`ChatGPT Image Sep 9, 2026, 11_04_51 AM.png`, not the unrelated flood photograph.
Its checksum and unverified geographic status are retained in the asset manifest;
the user's local source path is not embedded in application code.

Lab performance is not a claim about field p75 Web Vitals. Automated axe checks
are complemented by screenshot review, not a claim of comprehensive accessibility
certification. The source/export and all local checks remain distinct from a
published production release.

## Historical V2 Verification - 9 September 2026

The final tested competition export is `floodguard-offline-6d9365591289`.
The browser report was recorded at `2026-09-09T08:43:53.876Z`; its SHA-256 is
`8b6ca674749eaacea3fdd642ab4cf3f0fefabef9106140d4cf788f02e485453a`.

| Check | Result |
| --- | --- |
| ESLint and TypeScript | PASS, no lint warnings; web and contracts typechecked |
| Web unit/component tests | PASS, 213 tests across 34 files |
| Contract tests | PASS, 7 tests |
| Final competition static build and artifact checks | PASS, four routes; 58 mandatory chunks and one optional renderer excluded from precache |
| Public profile and same-origin profile transitions | PASS earlier in this V2 task; Public code remains unchanged by the final landing-only CSS fix |
| Real service-worker offline smoke | PASS on final export, four routes plus the legacy dashboard |
| Production security headers | PASS on final export, all four routes |
| Artwork integrity | PASS, 28 manifest assets and three editable-source hashes |
| Landing browser suite | PASS, 24 scenarios and 61 referenced screenshots |
| Automated accessibility | Zero axe violations; desktop has no incomplete items, mobile retains one incomplete source-caption contrast category |
| Dated manual review | Applicable to this exact source, CSS, assets and export; reviewed text pairs meet 4.5:1 |
| Local development preview | PASS at 127.0.0.1:4310: populated page, eight chapters, loaded aerial, ready single canvas, working story cue, no browser errors or framework overlays |

The browser suite covers the photographic selection/extraction, a genuinely
changing canvas, exact dry/flood landmark registration and held camera, reverse
seeking, settled rendering suspension, mobile and short/reflow viewports,
reduced motion, save-data, offline/reconnection, no JavaScript, unavailable
WebGL, cold deep links, renderer download failure, slow loading, context loss,
and eight mounted-map navigation cycles. Every final case records zero browser
errors, operational mutations and disallowed external requests.

The opening now reveals a constant-size image through clipping instead of
animating layout dimensions. Desktop static HTML and hydrated opening geometry
match within one pixel. A landing-only mobile bottom connectivity band replaces
the floating badge that covered part of a text row. Its closed/open states,
source-caption reachability, footer clearance, Public layout on exit, and landing
layout on return are browser-verified. Workspace connectivity styling is unchanged.

Local gzip-server measurements: initial transfer 1,107,198 bytes (1.056 MiB),
full-story transfer 2,137,243 bytes (2.038 MiB), deferred renderer 232,428 bytes
gzip, initial LCP 284 ms. Initial and full-story accumulated non-input layout
shift guards are 0.00378184 and 0.00603095. This conservative sum is not the
field Core Web Vitals maximum-session-window CLS metric. The closing scene
sample uses 33,308 triangles and 16 draw calls; rendering stops when settled.
These are unthrottled Chromium laboratory observations, not field p75 results.

The manual companion `manual-contrast-review.json` is dated
`2026-09-09 08:47:47 UTC` and has SHA-256
`c9883a88f33d1ce011f295577c7f3730c9d4bd74fc5368fa2724b4f1c218138e`.
It retains the mobile axe-incomplete record instead of converting it into an
automated pass. Its finding is limited to the inspected states and text pairs;
it is not comprehensive accessibility certification or owner art approval.

Durable evidence, current source snapshot, and preserved regression failures are
under `C:/Users/iputu/Documents/Project Support/FloodGuard/landing-2026-09-09-v2`.
The illustrative aerial and inferred architecture remain geographically
unverified. No backend/scientific acceptance, native Thai review, agency signoff,
production deployment, Git push or commit was performed. The original Documents
checkout and its pre-existing material remain untouched by this landing task.

## Historical V1 Verification - 8 September 2026

The following results apply to the previous six-chapter artifact only. They do
not constitute verification of the revised eight-chapter scene or stylesheet.

| Check | Result |
| --- | --- |
| ESLint | PASS, no warnings or errors |
| TypeScript | PASS, web and contracts |
| Web unit/component tests | PASS, 200 tests across 33 files |
| Contract tests | PASS, 7 tests |
| Public and competition static builds | PASS |
| Public profile route and cache isolation | PASS, no landing code emitted |
| Same-origin profile upgrades and downgrades | PASS |
| Production CSP smoke | PASS, all four competition routes |
| Offline browser and static smoke | PASS, four routes and 15 core assets |
| Original artwork integrity | PASS, all 19 listed files match size and SHA-256 |
| Local development preview | PASS, populated page, loaded hero, six chapters, no browser errors or overlay |
| Landing browser suite | PASS, all 19 scenarios, including eight mounted-map navigation cycles |
| First-viewport story cue | PASS, 11 geometry and accessible-name checks |
| Automated accessibility | PASS, zero axe violations on desktop and mobile; 30 rules passed in each |
| Manual contrast review | Applicable dated review, source/CSS hashes match; axe incomplete items remain visible in the report |

The competition build has 58 mandatory production chunks; its single optional
renderer chunk is excluded from precache. Public has 46 production chunks and
does not emit the landing shell, renderer or art. The final tested competition
cache identity is `800b64e50721`; Public is `d2b5ee756405`.

The final Chromium report was recorded at `2026-09-08T14:43:45.026Z` and contains
40 referenced screenshots. Every case has zero browser errors, operational
mutations and disallowed external requests. The repeated Public visits record
their approved basemap requests separately from the landing's request boundary.

Measured on the report's unthrottled local gzip server: initial page transfer
553.91 KiB; complete story transfer 1370.73 KiB; optional renderer 225.43 KiB gzip.
Local LCP was 260 ms. CLS was 0.003586 initially and 0.005025 after the story.
The sampled scene used 22,170 triangles and 14 draw calls, with frame counts
remaining stable while idle. These are laboratory observations, not field p75
claims. Reviewed text contrast ranges from 5.75:1 to 13.10:1 on the pale field;
the white primary-action label is 6.19:1 on teal.

Durable evidence is under
`C:/Users/iputu/Documents/Project Support/FloodGuard/landing-2026-09-08`.
The archive keeps the original final report, a copy with archive-local screenshot
paths, file hashes, the asset manifest, and the earlier reproduced Leaflet failure
for provenance. Its original final-report SHA-256 is
`95125416ea64ef2cdd57a5bbb7576a839125d3b6d6e38e8666fde6859b1a5102`.

No backend/scientific acceptance suite, field performance study, native Thai
review, agency acceptance, production deployment, Git push or release commit was
performed. None is implied by this frontend verification. The original checkout
and its pre-existing untracked material were preserved. Implementation remains
on the local `codex/connected-terrain-landing` branch for review.

## Input Identity

| Supplied material | SHA-256 |
| --- | --- |
| Production blueprint v1 Markdown | `8ecfc4ff6216fc39e6cb2c3bb1b4b3dd91f4897a5bffa4f615a0cd0561b68169` |
| Landing wireframe review HTML | `2b6070a837d9a87e3805514bf6bf90f0f0e8bcb1d565f1b5513606d40be9dad9` |
| Pasted production proposal | `a747f465a9253451a03c431b3582b55cf6c9b9fde54a7482cbc3210245056468` |
