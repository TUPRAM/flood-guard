# Engineering and integration contract

## Integrate; do not replace the project

Inspect the local repository, including uncommitted work. The public-default-branch inspection found an App Router app under `apps/web`, a profile-aware root, static export with trailingSlash, existing profile/offline/CSP scripts, and real Public/Command/Studio routes. Those findings are a starting map, not permission to overwrite a newer local landing implementation.

Keep source imports local to landing-related components. Prefer `apps/web/src/components/landing-v1/` or the existing local landing module. Use scoped CSS Modules or selectors rooted in `.fg-landing`. Do not change global heading/button styles and break application workspaces. Preserve current localization providers and font imports.

Suggested modules: LandingPage (semantic page), LandingHero, StoryNarrative, StoryStage, StoryPlate, StoryOverlay, StoryLabels, CharacterVignette, ExampleObservation, AccessFinding, ReviewBrief, ChapterNav, MotionPreference, and supporting sections. Do not fragment every span into a component. Data/story/geometry/assets are separate from the render logic.

## Source data

Copy/adapt the small `data/story.json`, `data/anchors.json`, and asset definitions into the app source; do not fetch the entire handoff from a runtime URL. The pure `story-math.mjs` functions and `StoryPlate.tsx` example demonstrate single-transform composition. Import/adapt them to the project's TypeScript/module rules. They are tested helpers, not a complete scene controller or production page.

The rendering data is not a geospatial API. Never submit native-pixel anchors, DEMO-R01, or story selection to FastAPI or the actual evidence registry. Keep all story interactions in a clearly named local namespace.

## Static-first architecture

Server-render the hero, headings, text, captions, role links, and no-motion sequence. The page is useful before animation code arrives. CSS should not default key content to opacity:0 pending JavaScript. Only add enhanced behavior after hydration and image readiness.

A practical desktop structure is a shared sticky visual area alongside a semantic sequence of chapter/substep content, driven by IntersectionObserver or one carefully scoped ScrollTrigger controller. The left rail supplies real headings and interactive content; the right scene reflects the current step. Maintain the reference composition at each settled step. On mobile/reduced-motion/no-JS, use ordinary in-flow illustrations with the same cached artwork URLs. Do not maintain two separately written story copies that drift; render from the same data.

Avoid duplicate accessible content when an enhanced sticky presenter is used. Choose one semantic source of copy and ensure inactive duplicate controls are neither focusable nor announced. Never leave opacity:0 controls in the tab order. A no-JS fallback is not an image of the whole page with text hidden elsewhere.

## State machine

Use the ordered nine frame IDs, grouped in four chapters, with H-01 outside the story. The content ID, chapter ID, water state, overlay state, portrait, and card are a coherent snapshot. The next water plate must decode before a transition commits, but the main reading flow and links cannot be blocked indefinitely.

A latest-request-wins transition controller is required. Quick forward/backward scrolling cancels an outgoing transition, resolves the intended destination, and never lets a stale decode promise overwrite it. Track a monotonically increasing request token or AbortController. Clean up effects/listeners on unmount and profile/viewport/motion changes.

Transitions between W2 scenes change overlays/card/portrait only. Do not remount/reload W2 every step or rebuild canvas content. Avoid per-frame React state. Use CSS/GSAP for bounded visual properties, with React updated only for a scene transition or explicit interaction. Keep motion deterministic; no random building placement or time-based water simulation.

## Motion tooling

Use the repository's current animation setup if it is suitable. Public default branch did not list GSAP; the local checkout may differ. Add GSAP only as a scoped dependency when needed and use the current available stable version consistent with the lockfile; do not silently upgrade Next/React. One state controller must coordinate all motion. Do not layer GSAP, a scroll-smoothing library, multiple independent IntersectionObservers, and another animation engine that each owns active-chapter state.

Use matchMedia/revert or equivalent cleanup for desktop, mobile, short-height and prefers-reduced-motion configurations. A manual Reduce motion control persists only a harmless local preference and updates immediately. Do not use an OS reduce preference as a reason to hide content. Stop nonessential effects when the tab or illustration is inactive. Native page scrolling, links and keyboard are never intercepted to trap the reader.

## Coordinate implementation

Every plate has native dimensions 1536×1024. A crop `[x,y,width,height]` defines the displayed rectangle. For a rendered crop at width W and height H with the SAME aspect ratio:

`screenX = (nativeX - cropX) / cropWidth * W`
`screenY = (nativeY - cropY) / cropHeight * H`

The image can be absolutely positioned using `width = nativeWidth/cropWidth * 100%`, `left = -cropX/cropWidth * 100%`, and analogous height/top percentages. The SVG uses exactly the same crop as its viewBox. DOM label centers use the same normalized projection. Do not combine this with an independent object-fit transform. For letterboxing/cover strategies, explicitly account for scale and offsets; the helper tests illustrate this.

Apply any hero/closing scale/translation to the common frame parent, never to the raster alone. Use `vector-effect="non-scaling-stroke"` or equivalent stroke sizing; label text is CSS-sized. SVG IDs must be unique per rendered copy (useId/sanitized IDs), not repeated globally in nine scenes.

Anchors and route need calibration. The authoring workbench loads original plates and exports revised native-pixel JSON. Inspect at desktop and mobile crop; a numerically valid path can still cross a garden. Null optional flood shoreline is valid. Never manufacture a flood analysis polygon simply to avoid an empty field.

## Images and loading

The app uses static export. Serve preoptimized local WebP variants directly with picture/img or the existing unoptimized Next Image configuration. Do not depend on `/_next/image`, server route handlers, cookies, or runtime image transformations that static hosting does not supply. Reserve width/height/aspect-ratio. Load the above-fold W0 image eagerly with one appropriate priority hint. Hero and S1 share its URL/variant when practical.

Use srcset/sizes based on actual art width, not the full viewport. Cropping can mean the image layer is wider than the visible crop; account for that in sizes. Below-fold portraits and W1/W2 are lazy/deferred and at most one upcoming state is prefetched near the story. Do not preload all 15 variants. A lower-bandwidth device may select smaller derivatives without changing narrative or geometry. The full-resolution sources remain for reference and potential per-asset fallback, not routine transfer.

Target added first-view illustration transfer roughly <=600–800 KiB on desktop and <=300–450 KiB on mobile depending on chosen density; target rather than claimed performance. The supplied 1536-wide W0 is about 534 KiB, and 768-wide W0 about 149 KiB. Do not count the total ZIP size as page payload. Measure actual requests with cache disabled, and report deferred SW transfers separately from initial rendering.

## Service worker and profiles

Read the local service worker and offline asset builder. Public default branch's `write-offline-assets.mjs` walks Next chunks and lists explicit core URLs. Simply adding pictures to public does not guarantee offline availability or cache-version invalidation. Add only approved runtime artwork files (or a selected offline width set) and their hashes to the competition offline strategy. Keep offline fallback image URLs available at whatever widths srcset can request, or provide an explicit offline source selection; do not claim offline completion when only one chosen online size is cached.

Do not eagerly precache every variant before first paint. Use the project's established cache lifecycle, a small initial set or an idle/deferred optional-artwork cache, and failure-safe fallbacks. Never cache the handoff references. Keep role separation and public-production exclusions. Include artwork changes in the cache version to avoid stale W0/W2 mixtures. Test installed-cache updates, not just one fresh online load.

The public-production root must still show PublicExperience as intended; no new planning/studio buttons or heavy landing artwork fetches should appear there accidentally. No confidential material is added by this illustration, but that does not relax existing cache or routing boundaries.

## CSP, links and semantics

Prefer same-origin local assets and existing local fonts. Do not introduce a remote texture, analytics SDK, font CDN, iframe, or unsafe-eval just for the landing page. DOM transforms must respect the existing CSP; verify the actual deployment response, not just dev-server behavior. Use plain Next/HTML links with the correct trailing slash. Do not weaken tests/security headers to accommodate a shortcut.

Observation inspection is a local details/dialog, no POST. Brief inspection opens accessible local content, no fake file download. Actual workspace links lead to existing pages; do not invent section hashes without checking they exist. If a specific deep link is unavailable, link to the workspace root with accurate label.

## QA integration hooks

Expose `data-fg-scene="<ID>"`, `data-fg-active-scene="<ID>"`, and a settled-state flag on the presentation. Provide a development/test-only review mode controlled by an explicit environment flag and client query `?fgReview=<ID>&fgStill=1`. Reading the query must not turn static export into a dynamic server route. Review mode renders the SAME components/layouts with one settled scene, ordinary typography and controls; it must not load a reference screenshot as the page.

`data-testid="fg-review-frame"` identifies its frame; set `data-fg-ready="true"` only after fonts and visible image decode settle. At mobile sizes allow content-driven height. Review hooks must be disabled in the normal public release. Browser capture harness exercises this mode. Separate production-path browser tests MUST still scroll the actual page, use four chapter anchors, test interactions, and verify profile behavior; fixtures alone do not prove integration.

## Commands and completion

Use actual discovered package scripts. Likely relevant: app lint/typecheck/test, competition build, public build, profile checks, CSP/offline smoke, and Playwright captures. Compare baseline failures with introduced failures. Do not run huge unrelated ML training or rewrite tests/lockfile to hide errors. No paid service, deployment, or push. Record the exact checks and visible outcomes in the execution report.
