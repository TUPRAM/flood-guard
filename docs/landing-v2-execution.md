# FloodGuard continuous neighborhood — execution record

## Authorized scope

The September 15 request authorizes a detailed editable Blender neighborhood and a continuous landing-page implementation. The user confirmed **wide drone overview → closer neighborhood framing**, followed by the artwork window shrinking to the right to create the left panel's space. The panel background persists; portraits persist while the speaker is unchanged. This supersedes the first handoff's restriction against constructing 3D assets.

Implementation checkout: `codex/landing-v1-artwork`, base `0b85f5bcd2fd0f9760df43b225ed691dcc977f5d`, in the registered `landing-v1` worktree. Existing v1 changes and review artifacts are preserved. No push or deployment is authorized.

## Production approach

- One Blender 5.1 master, authored through reproducible Python modules, with editable architecture, landscape, road, water, camera, and named attachment points.
- Rendered 3D for browser delivery; real HTML/CSS for narration and controls, and supplied transparent illustrated portraits. Browser delivery does not imply a live WebGL renderer.
- One dry camera approach sequence and matching dry/rising/flooded views from the final camera. Water is an illustrative scenario, not a hydraulic prediction or an operational road-closure claim.
- Native no-JavaScript, reduced-motion, enlarged-text, Public, Command, Studio, static-export, CSP, and offline behavior remain acceptance requirements.
- Blender is available at `C:/Program Files/Blender Foundation/Blender 5.1/blender.exe`; local rendering uses the verified RTX 3060 Laptop GPU with 6 GiB VRAM. This is headless Blender authoring, not a Blender MCP/live-UI verification claim.

## Work and evidence

1. Rechecked worktree provenance, implementation/controller, handoff clean W0 artwork, Blender executable, and GPU availability.
2. Delegated detailed architecture, shaped vegetation, and the persistent frontend timeline as independent bounded work.
3. Completed rendering, source exports, browser integration, visual refinement and verification, recorded below. The v1 results remain baseline evidence only.

## Implemented and reviewed

- Authored 26 houses and one clinic with batched tile courses, hip/ridge caps, teak balconies, shutters, glazing, foundations, porch details and clinic access details. Vegetation uses individually curved leaves, tapering branches, banana midribs and shaped shrubs.
- Two composition passes increased planting density, filled gardens, varied parcels, warmed the lighting and added transparent editorial terrain edges. The final master has 1,780 mesh objects, 10,082,162 vertices and 5,881,541 faces. These are source-scene counts, not a browser workload.
- Added a deterministic continuous timeline for all nine scenes. The camera approaches first; the artwork window then shrinks; paper slides into the resulting space; portrait and text follow. Background and portrait DOM elements persist. Narrow phones reserve panel space below the artwork; compact desktop previews retain the requested left/right composition.
- Added bounded image decoding, a retained loading poster and alpha-correct cross-fades. Exactly one physical state is visible at a reading hold. Registered world-derived SVG/HTML anchors appear after the camera settles.
- Rebuilt no-JavaScript/reduced-motion/enlarged-text flow around the same v2 artwork and retained the supplied transparent portraits.
- Retained optional, hashed, post-paint caching and Public exclusion. The optional inventory now derives from the v2 manifest plus eight retained portrait/decor files. Nine unused v1 plate variants remain as previous artwork on disk but are no longer proactively cached.

## Defects corrected during review

- First scene probe looked too sparse and regular: added fuller canopies, dense parcel borders, banana gardens, riverbank vegetation and less regular parcels.
- Adding editable Blender keyframes caused the first production batch to re-evaluate every shot at the source timeline's close/dry frame. Actual browser/artwork inspection caught it. Batch rendering now detaches animation only after saving the animated master; each render records and verifies camera position and water height. The incorrect batch was regenerated.
- Initial compact artwork was too small: the compact settled view now crops closer around both story locations while preserving their projected anchors.
- The phone observation label inherited a larger button font and collided with its route label: its font and offset are now explicit.
- Increased portrait scale within the persistent paper.
- Compared the modeled road elevation with the W2 water plane: the centerline is covered from approximately model X=-16.3 to X=12.4. Corrected the SVG affected span from route indices 5–10 to 3–10 so its endpoints match the rendered water crossing. These are invented model coordinates, not mapped closure evidence.
- Updated the root test's obsolete v1 plate expectation to the actual wide v2 poster. The full web suite then passed.
- Moved the selected-area control outside the cropped world into the artwork window. On compact/mobile layouts, the online-status control now sits above the story content, and its closed hitbox follows its visible size.
- Made the story explanation a named, keyboard-focusable region while its content is interactive. Long text can scroll inside the stable panel; hidden entrance content stays outside normal Tab navigation.
- Kept critical image requests ahead of background preloads. Water-state preparation begins near the end of the camera approach; initial cold image transfers fell from 7,121,672 to 4,747,143 encoded bytes in the local no-cache measurement before the final interaction-only fixes.
- The expanded browser suite exposed native reload restoring the prior server-rendered flow's scroll position over the enhanced story. Enhanced mode now owns history restoration, aligns an initial hash again after loading, cancels that late alignment on user input, and computes target positions with the sampler's exact viewport unit.
- Brief focus could programmatically scroll the hidden-overflow stage sideways on a phone. The stage now clips without being a scroll container, brief opening scrolls only its panel, and Escape restores focus without scrolling ancestors.
- Preserved the first expanded browser result as iteration evidence: 14/19 checks passed before the reload, focus, PWA hitbox and no-JavaScript harness corrections. This is not the final acceptance report.
- Visual inspection of the initial 16-frame approach found doubled roof edges despite passing interaction checks. Added three actual projected ground references per camera, affine registration of adjacent images before blending, and six independent ground/roof probes. All 16 projections are distinct. Worst adjacent midpoint residual is 2.72 native pixels on ground and 3.39 at a clinic roof. Settled plates remain untransformed. A soft edge mask removes the rectangular seams between transformed raster frames.
- Projection extraction initially exposed a stale Blender dependency-graph camera matrix. Explicit view-layer evaluation corrected it; validation now rejects frozen/degenerate camera triangles. The saved master and all 19 PNG/WebP hashes remained unchanged.
- The final contact sheet exposed a first-reading-scene portrait decode race. Both portraits now decode in the bounded queue after first paint and retain their sources. Capture readiness requires the assigned portrait, verifies its clipped geometry, and awaits actual image decoding before capturing. The first desktop resident hold was reopened and visually confirmed.

## Verification

- Full lint: passed.
- Full contracts/web type checking: passed.
- Full web tests: **242 passed across 39 files**, including three camera registration tests. A final focused landing/root run passed **26 tests** after the portrait refinement.
- Contract tests: **7 passed**.
- Optional artwork inventory/worker tests: **8 passed**.
- Local development browser: meaningful page and controls rendered; no error overlay during the initial check. Turbopack could not resolve this redirected Windows worktree; `next dev --webpack` started successfully. Development-only captures are iteration evidence, not final acceptance.
- Production profile, offline, CSP, continuous browser and render-provenance checks are recorded below.

## Production verification

- Render/source checks: **passed**, 19 distinct native RGBA renders, 16 actual camera positions, three registered water levels, finite in-frame anchors, exact PNG/WebP hashes. V2 runtime assets: **6,436,484 bytes**.
- Public and competition profile builds, artifact boundaries, Public browser navigation, same-origin cache downgrade/upgrade and offline staff readiness: **passed**. The Public export contains zero landing artwork.
- Offline: **passed**, all four app routes and optional artwork available from the versioned worker cache; basemap failure behavior preserved.
- CSP: **passed**, all four routes plus map recovery and opt-in Public location behavior under production headers.
- Competition static export was rebuilt after visual and interaction refinements. Final browser captures and the artifact identity refer to that output.

## Final acceptance and artifact identity

Final competition cache: **`fd9e33e50178`**. The preview's HTTP response matches the exported `index.html` byte-for-byte.

- Index SHA-256: `58334082A2281221B836363A8BB117FE7D99C8D2F04E845D30B42CBF6808E117`
- Editable master SHA-256: `4BD1F8706A90830A3932F27C2368042D2E66E749EA17ACC6F405DBD05D88A921`
- Browser report SHA-256: `33E82C570ACE0EAAF030227D6D571E211B68CCE4C491F89EF308F440EED71640`
- [Complete machine-readable identity](../outputs/landing-v2-assets/final-artifact-identity.json)

| Check | Actual result | Evidence |
| --- | --- | --- |
| Web unit suite | 242 passed, 39 files | [Log](../outputs/landing-v2-assets/test-web-final.log) |
| Final focused landing/root suite | 26 passed, 4 files | [Log](../outputs/landing-v2-assets/test-focused-final.log) |
| Contracts / optional inventory-policy tests | 7 / 8 passed | Earlier execution results; no contract/worker behavior changes in final visual refinement |
| Lint | Full lint and final changed-source lint passed | [Full](../outputs/landing-v2-assets/lint-final.log), [closeout](../outputs/landing-v2-assets/lint-focused-closeout.log) |
| Types / final static build | Passed | [Types](../outputs/landing-v2-assets/typecheck.log), [build](../outputs/landing-v2-assets/build-final.log) |
| Public/competition profiles and transitions | Passed, zero Public landing artwork | [Log](../outputs/landing-v2-assets/profiles.log) |
| Offline / legacy dashboard / basemap failure | Passed | [Log](../outputs/landing-v2-assets/offline-final.log) |
| Full-route production CSP | Passed | [Log](../outputs/landing-v2-assets/csp-final.log) |
| Final continuous browser acceptance | **21 passed, 0 failed** | [Report](visual-qa/landing-v2/browser-acceptance-production/continuous-browser-results.json) |
| Final natural worker artwork cache | **27 assets, 7,200,977 response-body bytes**, hashes verified, after FCP | [Report](visual-qa/landing-v2/browser-acceptance-production/service-worker-artwork-transfers.json) |
| Native renders / camera registration / exported images | Passed | [Report](../outputs/landing-v2-assets/render-validation.json) |

The final browser suite produced 69 captures and a 24-second native-scroll recording. It covers 1672×941, 636×728, 390×844, a 320×800 phone, an 844×390 landscape, nine story states, forward/reverse scroll, chapter links/history/reload, dialog/brief focus, keyboard panel scrolling, reduced motion, no JavaScript, enlarged text, failed-artwork fallback and production CSP. The final report includes decoded-image and clipped-portrait geometry evidence. No page errors, CSP violations, operational submissions or geolocation calls occurred in those checks.

### Local cold measurements

| Viewport | FCP | CLS | Opening encoded image bytes | Image bytes complete by FCP |
| --- | ---: | ---: | ---: | ---: |
| 1672×941 | 252 ms | 0.002762 | 5,148,187 | 332,940 |
| 390×844 | 236 ms | 0.036722 | 5,148,187 | 332,940 |

Fresh local Chromium contexts, service workers blocked, HTTP cache disabled. The opening observation includes deferred camera/portrait preparation. Opening-plus-story image transfers were 8,689,948 encoded bytes; cache disabling exposes repeated decoder/display requests. These values are distinct from the deduplicated 6,436,484-byte neighborhood export and the 7,200,977-byte optional worker inventory. They are measured local observations, not field or physical-device performance claims.

## Changed-file map

- Editable asset and source: `assets/floodguard-neighborhood/`, `tools/neighborhood/{architecture,vegetation,build_scene,package_renders,validate_renders,review_board}.py`.
- Runtime artwork and projected anchors: `apps/web/public/landing/floodguard-v2/`.
- Continuous behavior/components: `apps/web/src/components/landing-v1/{landing-experience,continuous-stage,story-plate,scene-frame}.tsx`, their CSS modules, and `apps/web/src/lib/landing-v1/{timeline,neighborhood,story}.ts` plus tests.
- Existing v1 integration retained: root competition/Public separation, optional artwork cache component, worker/profile/offline scripts, static review server and original handoff/artwork records.
- Final acceptance runner: `apps/web/scripts/landing-continuous-smoke.mjs`. The older `landing-browser-smoke.mjs` remains the v1 baseline and is not the v2 acceptance command.
- Review and provenance: `docs/landing-v2-*.md`, `docs/visual-qa/landing-v2/`, `outputs/landing-v2-assets/`.

Work remains local and uncommitted on the existing landing branch; unrelated work was preserved. No push or deployment was performed.

## Preview and reproduce verification

The local production preview is running at **http://127.0.0.1:3100/**. To restart it if stopped, from the landing worktree root:

```powershell
pnpm build:web
node apps/web/scripts/preview-static.mjs 3100
```

For development in this redirected Windows worktree:

```powershell
pnpm --filter @floodguard/web exec next dev --webpack --hostname 127.0.0.1 --port 3101
```

From `apps/web`, rerun the current landing acceptance against the production preview:

```powershell
node scripts/landing-continuous-smoke.mjs --base-url=http://127.0.0.1:3100 --output=../../docs/visual-qa/landing-v2/browser-acceptance-production
```

See the [visual review](landing-v2-visual-review.md) for the chosen rendered-3D delivery, responsive differences, remaining minor interpolation limits and testing boundaries. See the [source README](../assets/floodguard-neighborhood/README.md) for Blender reproduction.

## 2026-09-15 — Requested landing UI cleanup

Removed the screenshot-highlighted skip-to-workspaces link, hero eyebrow, hero action buttons, hero historical-demo status line, floating availability control, and artwork scenario caption. The animated stage and readable/reduced-motion/no-JavaScript frames now apply the same removals. Removed the associated unused CSS. Header navigation, closing actions, persistent story panel, route graphics, portraits, and accessible scene descriptions remain.

The availability component still mounts and runs its existing service-worker effects. A landing-scoped CSS rule hides its UI; Public, Command, and Studio retain visible controls. Updated the profile-transition browser check to activate a pending competition update through `/public/`, where the controls remain available. This also works while the previous Public worker still excludes staff routes.

Verification performed for this cleanup:

- Focused Vitest: **13 passed in 2 files** (`scene-frame.test.tsx`, `page.test.tsx`).
- ESLint: **passed** for changed TSX/tests/browser scripts, including the final continuous-stage conditional.
- Public and competition production builds, TypeScript compilation, profile artifact checks, Public browser smoke, and both directions of offline profile transition: **passed**. [Profile verification log](../outputs/landing-v2-cleanup/profile-verification.log).
- Final competition static export after removing a hidden duplicate hero eyebrow: **passed**; worker cache identity `eef688b01ca8`. [Final build log](../outputs/landing-v2-cleanup/final-build.log).
- Focused browser verification: **7 passed** — desktop 1672×941, phone 390×844, reduced motion, no JavaScript, and retained availability controls on all three workspace routes. No page errors in the four landing cases; no horizontal overflow. [Browser report](visual-qa/landing-v2/cleanup/cleanup-browser-results.json).
- Opened and visually reviewed all six final screenshots: desktop/phone opening and settled first story panel, reduced-motion opening, and no-JavaScript opening. Settled story captures wait for artwork readiness. [Desktop opening](visual-qa/landing-v2/cleanup/desktop-hero.png), [phone opening](visual-qa/landing-v2/cleanup/phone-hero.png), [desktop story](visual-qa/landing-v2/cleanup/desktop-story.png), [phone story](visual-qa/landing-v2/cleanup/phone-story.png).

During the focused check, a hidden duplicate eyebrow was found and removed. The capture command was adjusted to scroll to the native story anchor on phones, whose compact header omits the desktop Story link. The final checks pass. The previous comprehensive 21-check browser suite is historical; it was not rerun for this small cleanup. No asset, camera, or timeline changes were made. No push or deployment was performed. The local static preview remains at http://127.0.0.1:3100/.

## 2026-09-16 — Production release preparation

The user authorized committing and merging this landing page and switching `https://flood-guard-tau.vercel.app/` to it. GitHub's default and production branch is `master` (there is no `main` branch), so the authorized merge targets `master`. Refreshed `origin/master` and the landing base both resolve to `0b85f5bcd2fd0f9760df43b225ed691dcc977f5d`; no upstream merge was required.

The release includes runtime images, the responsive/continuous page, native readable fallbacks, profile/offline integration, the complete original handoff, reproducible Blender source scripts, and selected final verification evidence. The generated 188,853,451-byte Blender master remains local and is excluded from Git; its checksum and reproduction instructions are in `assets/floodguard-neighborhood/README.md`. Raw renders, earlier screenshot iterations, and duplicate recordings remain local. The supplied CRLF asset manifest is explicitly byte-preserved by `.gitattributes` so its handoff checksum survives checkout.

Fresh `pnpm verify:frontend` completed successfully before commit: zero-warning lint, TypeScript, 7 contract tests, the full web suite, Public and competition builds/artifact checks, Public browser checks, both service-worker profile transitions, all four offline routes, and production-policy/CSP browser checks. See [release verification log](../outputs/landing-v2-release/frontend-verification.log). Source changes pass the staged whitespace check; raw supplied handoff files and captured logs are retained verbatim, including their original whitespace.

Production deployment identity, merge commit, hosted CI, and live browser results will be recorded in a durable release receipt under the local Project Support/FloodGuard/releases directory after the merge. This preparation entry does not claim a deployment has occurred.
