# Desktop V3: One Continuous Aerial World

The 12 September desktop styling revision is recorded at the end of this file.
The 10 September results below remain a historical verification record.

## Request and Scope

This desktop revision follows the user's 10 September 2026 request to study the
Illoca recording and implement a continuous far-aerial, close-dry and flooded
story. Mobile layout and V2 mobile artwork are deliberately unchanged. Existing
static/reduced-motion/offline reading paths and workspace links remain available.
No deployment, operational action or geographic validation is authorized by the
reference material.

## What the Reference Actually Does

The supplied `Recording 2026-09-09 170334.mp4` is a 1916x908 H.264 recording,
approximately 90.709 seconds long, with a 30 fps video cadence. Its SHA-256 is
`61beddd01866da2928df6d87154dfe4b9c34d476fc54b69c45fd0f32346e9669`.
The local analysis contains 112 unique native-resolution sampled frames,
including half-second samples around the transitions, eight contact sheets and
five hash-bearing metadata records. It is a detailed sampled-frame analysis,
not a claim that all 2,717 video samples were independently reviewed.

| Recording interval | Observed mechanism |
| --- | --- |
| 0-9 seconds | A persistent architectural scene occupies approximately the lower 48 percent of the page, below opaque hero copy. Small viewpoint changes are visible. |
| 12-15 seconds | The title leaves and the visual aperture expands upward; this is page masking/reveal, not just image scaling. |
| 16-21 seconds | The camera approaches and rises over the desk. Perspective, occlusion and relative object positions change. |
| 24-33 seconds | An opaque left text column takes about a third of the page while the same scene continues on the right. |
| 35-45 seconds | Full-width imagery returns and the camera approaches the same paper and developing model. |
| 47-72 seconds | Alternating side text panels cover parts of the continuing scene and then leave. |
| 74-79 seconds | A full-area open-letter section appears, then the recording continues to pricing and the footer. |

The full-screen text pause followed by re-exposing the terrain is the user's
requested adaptation. It is not described as a literal sequence observed in
Illoca's feature section.

Live inspection of [Illoca](https://illoca.unseen.co/) also confirmed one WebGL
canvas and requests for `scene.glb`, `building.glb`, additional scene GLBs,
KTX2 textures, and Draco/Basis decoder resources. None of those proprietary
models, textures, fonts or animation files is copied into FloodGuard.

## How This Type of Animation Is Built

The visual style is often called 2.5D, but the inspected reference uses a real
3D scene presented through a controlled camera and HTML layers. A flat aerial
cannot reveal reliable hidden walls as the camera moves.

An authored production pipeline can export meshes, materials, cameras and
animation clips into `.glb`/`.gltf`; Three.js loads or exports that format.
[Three.js GLTFExporter documentation](https://threejs.org/docs/pages/GLTFExporter.html)
describes the scene and animation content supported by the format. Animation
clips can be played by the
[Three.js animation system](https://threejs.org/manual/en/animation-system.html).

For this implementation, original geometry, materials and the camera path are
editable TypeScript. A pure progress sampler drives the camera and water, so
backward scroll and direct seeks do not depend on animation history. GSAP links
the clock to measured native scroll positions using a scrubbed timeline, as
described in its [ScrollTrigger documentation](https://gsap.com/docs/v3/Plugins/ScrollTrigger/).
Repeated city buildings share instanced geometry to keep draw calls bounded;
this follows the purpose of [Three.js InstancedMesh](https://threejs.org/docs/pages/InstancedMesh.html).

## FloodGuard Composition

- One continuous original terrain surface, town, river, fields and wooded edge.
- A detailed neighborhood embedded in the larger town from the first frame.
- One perspective camera with a restrained fixed field of view. The camera
  approaches the existing neighborhood rather than swapping a photo for a model.
- An opaque HTML interlude covers the still-mounted world. It is a reading
  section, not an interactive modal and not a renderer replacement.
- Dry and flooded close views use identical geometry and camera. Flooding is
  held at zero until the interlude has cleared, then remains through the close.
- Small fine-pointer camera offsets give the initial hero a responsive drift.
  They settle, reset on leaving, and stop while hidden or fully covered.

Desktop progress: far/reveal 0-.04; approach .04-.18; dry hold .18-.22;
interlude enters .22-.24, holds .24-.28 and exits .28-.32; flooding .32-.42;
post-flood overview .42-.55; existing role story .55-1 with water retained.

The original static semantic chapters remain the accessible reading source.
Desktop cinematic copy is a non-interactive visual presentation of that story.
The mobile and fallback images are not regenerated as part of this revision.
The desktop hero omits the duplicate introductory paragraph and CTA row while
retaining the header's demo and workspace entry. Its responsive height keeps
the aerial near the lower half of the initial desktop viewport. Mobile retains
its previous copy, actions, layout and artwork.

## Source Limits

The NYC references inform density, scale and aerial composition only. Neither
their geometry nor map imagery is imported. The supplied Mae Sai images remain
reference material; their provenance does not establish a surveyed or
photogrammetric model. This world is explicitly a Mae Sai-inspired illustration.
The water is an authored scenario, not a hydraulic simulation, measured flood
depth, forecast or verified road closure. Scrolling does not write reports,
request location, dispatch aid, or change evidence.

## Acceptance Contract

Fresh desktop verification must establish full-frame far, approach, close-dry,
opaque interlude, rising-water and post-flood views in an actual scroll recording.
The same canvas and world must persist; dry/flood camera and landmarks must
match; reverse seeks and pointer reset must be deterministic. The interlude
must really cover the scene and its text must fit at 1366x768 as well as larger
desktop sizes. Failure and static policies must retain readable content.

V3 intentionally loads its optional renderer for the initial interactive hero.
Its declared lab budgets are therefore 2 MiB initial transfer, 3 MiB full tested
story, at most 250,000 visible triangles and 45 draw calls. The accumulated
non-input layout-shift guard stays at 0.1. These are local acceptance budgets,
not field p75 metrics or a promise of the same frame rate on all hardware.

The dedicated browser harness is `apps/web/scripts/desktop-landing-smoke.mjs`.
V2 mobile preservation is checked against the 9 September archive, including
asset hashes and representative screenshots. Final results are recorded only
after the new export and actual browser motion have been verified.

## Reproduce

Stop the development server before running profile builds. These builds replace
the generated Next output and temporarily isolate staff routes; a concurrent
development process can regenerate an incompatible route validator.

From the repository root:

```powershell
pnpm --filter @floodguard/web art:desktop
pnpm verify:frontend
$env:FLOODGUARD_BROWSER_EXECUTABLE = Join-Path $env:ProgramFiles 'Google/Chrome/Application/chrome.exe'
$env:FLOODGUARD_DESKTOP_EVIDENCE = 'test-results/landing-v3/recheck-desktop'
pnpm --filter @floodguard/web qa:desktop --desktop-only
Remove-Item Env:FLOODGUARD_BROWSER_EXECUTABLE
$env:FLOODGUARD_DESKTOP_EVIDENCE = 'test-results/landing-v3/recheck-mobile'
pnpm --filter @floodguard/web qa:desktop --mobile-baseline
pnpm --filter @floodguard/web dev --hostname 127.0.0.1 --port 4310
```

The installed-browser override is optional for functionality but important when
measuring GPU motion on this machine. The bundled headless Chromium uses
SwiftShader here; installed Chrome and Edge expose the NVIDIA D3D11 renderer.
The test report records the actual driver, so software and hardware traces are
not treated as interchangeable. The V2 comparison uses the dated local archive;
set `FLOODGUARD_V2_BASELINE` when that archive is stored elsewhere.
The two mobile-baseline cases require the actual browser to match the archived
Chromium 149.0.7827.55 version. The desktop-only group now has 25 cases, including
the additional actual-Tab focus regression. Group switches are mutually
exclusive, and an empty named selection is rejected. The recorded final result
below combines the original 24 desktop cases with the separately verified
keyboard regression; it does not relabel an earlier raw report.

## Verification - 10 September 2026

The tested competition export is `floodguard-offline-7f184ca03cf1`. The Public
profile built in the same verification cycle is `3a82f9477fd4`. Application
source and art were frozen before the final browser captures. The local preview
is `http://127.0.0.1:4310`; use a desktop window at least 1100x700 for animation.

| Boundary | Observed result |
| --- | --- |
| ESLint and TypeScript | PASS on the final application source; no lint warnings |
| Web unit/component tests | PASS, 226 tests across 36 files |
| Contract tests | PASS, 7 tests |
| Public and competition builds | PASS, profile artifacts, Public browser entry, and same-origin cache transitions |
| Real service-worker offline checks | PASS, four routes and the legacy dashboard |
| Production security headers | PASS, all four competition routes |
| Desktop browser behavior | PASS, all 24 desktop cases in the completed hardware run |
| Keyboard focus regression | PASS, actual Tab navigation reveals visible, unobscured story controls |
| Preserved mobile behavior | PASS, both mobile/narrow cases against the matching Chromium 149 baseline |
| Map navigation lifecycle | PASS, eight repeated mounted-map navigation cycles |
| Graphics integrity | PASS, populated canvas pixels, one world/canvas, identical dry/flood camera and landmarks, retained flood at closing |
| Artwork integrity | PASS, four V3 frames and source hashes; all 28 V2 assets and the V2 manifest unchanged |
| Development preview | PASS, one ready canvas, eight chapters, working native story link, no console errors or development warning overlay |

The desktop cases include six viewport sizes from 1280x720 to 2048x1152, actual
scrolling, arbitrary reverse seeks, five cold anchors, pointer reset, idle and
hidden suspension, full opaque interlude coverage, resize policies, failed
downloads, unavailable WebGL, context loss, and static/reduced-motion/offline
paths. Mobile was regression-checked, not redesigned. The hero's scene aperture
is measured from actual clipping and content bounds rather than assumed from CSS.

The final Chrome 152 hardware capture identifies the NVIDIA RTX 3060 Laptop GPU
through D3D11. It transfers 1,573,354 bytes initially and 2,029,087 bytes through
the tested story. Local LCP is 1,120 ms; accumulated non-input layout shift is
0.0116037144. Sampled scroll rAF gaps have approximately 6.1 ms medians and
6.2-6.3 ms segment p95 values. A worst 72.7 ms gap at the first flood rise is
retained. These are unthrottled local observations, not universal FPS, field p75,
or a low-end hardware guarantee. The 34.48-second browser video shows the actual
scroll sequence and reverse checks; it is not a separately authored animation.

### Preserved Exceptions and Limits

The complete hardware report remains marked FAIL (25/26): its cross-browser
mobile screenshot comparison against historical Chromium 149 exceeded the
unchanged mean-RGB threshold. Diagnostic regions localize most of that difference
to the photographic image resampling, not the HTML layout. Both mobile cases
pass in the original browser configuration. The final acceptance is therefore
the explicit composite of 24 desktop hardware cases plus two matching-browser
mobile cases, not a claim that the raw hardware report passed all 26 cases.

An earlier interrupted hardware run recorded one unexpected WebGL context loss.
The page restored its still-illustration fallback. The loss did not reproduce in
the isolated viewport retest or the completed desktop run; its cause remains
unestablished. The raw failure is retained. Software SwiftShader recordings are
also retained and are substantially slower than the hardware capture.

The development preview exposed a missing React key on the server-rendered
poster slot. That warning was fixed and verified in a fresh development browser.
Earlier timing assertion failures were traced to GSAP's integer endpoint and
six-decimal clock rounding; the oracle was corrected without widening its
2e-6 tolerance. An offline copy assertion was updated to the retained workspace
section after the duplicate desktop hero CTA was intentionally removed.

Axe reports no violations, but layered-background contrast checks remain
incomplete and require the dated manual companion. Keyboard focus on initially
transparent chapter controls visibly reveals them; controls are not focusable
under the opaque interlude. This is bounded local accessibility verification,
not screen-reader certification or a cross-browser accessibility guarantee.

Durable source, reference analysis, raw reports, earlier failures, actual motion
and hash manifests are retained under
`C:/Users/iputu/Documents/Project Support/FloodGuard/landing-2026-09-10-v3-desktop`.
No deployment, Git push, commit, mobile redesign, geographic validation,
hydraulic validation, scientific acceptance or agency approval is claimed.

## Desktop Styling - 12 September 2026

Scope: adjust the desktop identity, page texture, hero copy, scene aperture and
native browser scrollbar. The authored world, camera sampler and V3 artwork are
unchanged. Mobile layout is preserved, not redesigned.

- The desktop header and footer use Public's `/floodguard-logo.png` shield.
  Desktop colors follow the Public primary blue `#0f4c81`, canvas `#eff4fb`,
  neutral ink `#0f172a`, and orange accents. Small warning copy uses a darker
  orange to retain contrast. The Public app itself was not rethemed.
- The supplied topographic PNG is mechanically encoded as
  `/landing/topography.webp`, 1619x971, 86,838 bytes. CSS blends it with the Public
  canvas color and a 65 percent paper overlay. It is decoration, not geographic
  data. Neither the bitmap nor the desktop logo background is requested by the
  tested mobile viewports.
- The desktop hero contains only the requested two-line headline, without the
  repeated brand heading, eyebrow, introduction, actions or scroll cue. The
  header navigation and workspace entry remain available.
- The hero uses the existing licensed Inter Variable at weight 500. Live
  inspection identified Illoca's exact font as F37 Analog Medium, weight 500,
  in its [entry stylesheet](https://illoca.unseen.co/_nuxt/entry.CIVqmn_L.css).
  [F37 Analog](https://f37.com/fonts/f37-analog) requires an appropriate commercial
  webfont licence; no proprietary font files were copied or licence assumed.
- The desktop animation toggle is removed from view and keyboard navigation.
  Eligible desktops animate from the beginning even when an old local toggle
  preference was stored. OS reduced motion, data-saving, offline and renderer
  failure policies remain in force.
- Initial map framing is 24px left/right/bottom. Once revealed, all four scene
  edges are 24px inside the document viewport. The bottom clip accounts for the
  sticky stage's initial offset below the header; these measurements exclude
  the native scrollbar gutter.
- The existing native scrollbar keeps native drag and keyboard behavior. Its
  blue thumb fades after 900ms idle through a 320ms color transition, reappears
  on scrolling or edge hover, and resets correctly across desktop breakpoints.
  Forced-colors mode keeps platform colors; reduced motion removes the fade
  transition. No custom scrolling engine or replacement scrollbar is introduced.

Source image SHA-256:
`965d816dfae8f0d46eb882206508b00c0224a63c78e65ff7a17ce735f23bca6b`.
WebP SHA-256:
`d8c69347407a862362476490eef12798777f02dfd5a6a73271af9a04eb6f41e1`.

### Scoped Verification

The new `apps/web/scripts/landing-style-smoke.mjs` verifies exact hero copy,
Public identity assets, background delivery, viewport-relative aperture,
nonblank persistent canvas, native scrollbar fade/drag/keyboard/resize behavior,
legacy preference handling, reduced motion, unavailable WebGL, no JavaScript,
and 390px/320px mobile preservation. Raw evidence is under
`apps/web/test-results/landing-style-2026-09-12/`.

The development matrix passed 8/8. All four matching-browser mobile screenshots
are byte-identical to the pre-edit development baseline. The competition build
passed with cache `floodguard-offline-4178a03f36ec`; its profile artifact check
also passed. All six desktop/fallback production cases passed. Web tests passed
226/226 across 36 files; ESLint and TypeScript passed. Real service-worker checks
passed for four routes plus the legacy dashboard. All four competition routes
also rendered under production security headers.

A cross-environment production-vs-development mobile comparison is retained as
a failed raw report, not rewritten: production includes the existing Online
PWA status band while development omits it. The current production 390px hero
and Studio captures are instead byte-identical to the prior 10 September
Chromium 149 production captures. A fresh matching-production run passed; its
evidence is in `production-matched-mobile/`. This is not a font, image decoding,
or mobile layout regression. The harness now rejects mismatched baseline
environments and supports `--desktop-only` for production desktop verification.

Axe reported zero violations in the focused desktop checks, but image-background
contrast incomplete nodes remain explicitly unverified by that automated tool.
Separate rendered-background sampling verified the darkest tested texture pixel
at RGB(210,215,222), giving the small orange text at least 4.563:1; solid-paper
callouts measured 5.974:1. This is bounded local review, not blanket accessibility
or screen-reader certification. Desktop screenshots were manually reviewed.

No deployment, commit, push, new font licence, mobile redesign or 3D art change
was performed in this styling pass. Start the preview with the reproduction
command above; stop it before running another profile build.
