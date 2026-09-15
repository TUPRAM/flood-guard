# FloodGuard landing v1 execution record

## Goal and boundaries

Implement the supplied editorial storyboard using clean W0/W1/W2 artwork, transparent portraits, semantic responsive HTML and registered SVG. Preserve Public/Command/Studio, static export, profiles, CSP, offline policy, fonts/localization and unrelated work. Illustration-only interactions; no geolocation, incident submission, forecast or dispatch. No push or deployment.

## Baseline

- Implementation worktree: `C:\Users\iputu\AppData\Local\CodexWorktrees\flood-guard\landing-v1`.
- Branch: `codex/landing-v1-artwork`; base `0b85f5bcd2fd0f9760df43b225ed691dcc977f5d` (already-local origin/master).
- Original Documents checkout preserved at master `58cb508` with unrelated untracked .env.local, .vercel, apps, dist, node_modules, packages and storyboard outputs. Handoff ZIP extracted under handoff here as requested, then copied into implementation worktree.
- Existing fg-landing worktree preserved at landing-page `0fec74b`, with dirty next-env.d.ts and untracked hero artwork. No branch switched in either existing checkout.
- New registered worktree is necessary because original checkout lacks tracked current web app and old landing branch lacks latest Public/map fixes. Latest base retains chooser entry and removes old procedural landing.
- Applicable authority: supplied working/hygiene agreements; repository root AGENTS.md; explicitly invoked implementation master and linked specifications. No deeper tracked AGENTS found.
- Stack: Next 16.2.6, React 19.2.4, pnpm 10.34.5, TypeScript 5.7.3, Playwright 1.61.1, Vitest 3.2.4. Existing local Inter/Manrope/Plus Jakarta/Noto Sans Thai. No framework upgrade or new animation dependency planned.
- A separate clean-base full test run was not recorded. The first integrated web suite passed all 207 existing tests; the final suite, including landing coverage, passed 227. Source-package helper checks are reported separately.

## Decisions

- Use native 1536x1024 plates as spatial authority. Reference PNGs remain outside public. Use supplied WebP derivatives with one crop transform for raster/SVG/labels.
- Responsive static document is the fallback; enhance desktop only when viewport, motion preference and hydration permit. Exact W2 URL reused for all later beats.
- Native scrolling and latest-request-wins fade-to-paper state swaps; no smooth-scroll library, WebGL or added motion dependency.
- Public root uses build-time entry isolation. Competition artwork cache is optional and deferred; public export prunes landing assets. All artwork hashes participate in cache version.
- Review query mode requires NEXT_PUBLIC_FLOODGUARD_LANDING_REVIEW=1. Capture the same components at all six specified viewports and test normal scroll separately.

## Gates

- [x] A: local audit and package verification
- [x] B: selected runtime assets installed without conflicts
- [x] C: semantic static frames built
- [x] D: native-pixel route/crop calibration reviewed
- [x] E: nine states/four chapters and local example interactions
- [x] F: motion and fallback behavior integrated
- [x] G: supporting sections and genuine links
- [x] H: project/profile/offline/CSP/browser checks
- [x] I: two capture-inspect-refine rounds

## Visual findings

Opened all nine desktop references, all nine mobile references, the three clean plates and both transparent portraits. Opened the supplied QA workbench in a browser and inspected W2 with the seed route overlay. No complete reference screenshot is runtime content.

Round 1: captured 54 shared-component frames (nine scenes at all six specified viewports) into outputs/landing-v1-review/round-1. Inspected hero, everyday, affected connection and analysis at native 1672x941, plus mobile everyday and brief. Largest differences: hero body covered by town; analysis card covered clinic; long heading/body collided with portrait; mobile selection button inherited an oversized font; crop extended below image.

Round 2: captured another 54 frames into outputs/landing-v1-review/round-2. Reduced hero heading to the reference scale, corrected hero crop, tightened finding card without hiding its rows, reduced portrait footprint, corrected mobile label font and crop. This review then identified road-trace drift approaching the clinic, a clipped mobile hero clinic, and report/selection label spacing to fix.

Round 3 and final refinement: corrected the route to follow the pavement and clinic driveway; recalibrated mobile/hero crops; separated report and selection labels. Refreshed all 54 final captures after correcting laptop typography/card spacing, hero clinic-label clearance, desktop motion-control overlap, the resident question extending onto artwork, the mobile report label hiding its hollow pin, and desktop captions colliding with the resident card. Detailed scene review and remaining aesthetic differences are in `docs/landing-v1-visual-review.md`; the side-by-side gallery is `outputs/landing-v1-review/comparison.html`.

Registration uses native 1536x1024 coordinates: home gate (453,433), clinic entrance (1227,629), a 17-point road trace, affected segment indices 3–12, and report (825,703). Raster, SVG and DOM labels share one cropped plane. W2 remains the same physical plate through the closing scene. The mobile report label uses a different text-box alignment to expose its pin; no independent image/SVG scaling is introduced.

## Verification log

- Package integrity: node tools/verify-package.mjs, exit 0: 76 hashes, 24 originals, 15 runtime raster variants, 9 scenes/4 chapters.
- Toolkit helper tests: node --test implementation-kit/story-math.test.mjs, exit 0: 12 tests. These are source-package checks only.
- Asset installer: dry run reviewed, then --apply; exit 0, all 18 new destinations, no overwrite conflict. 15 WebPs total 3,485,414 bytes. References stay outside public.
- pnpm install --frozen-lockfile: exit 0, no lockfile change.
- First web typecheck found two tuple/undefined type errors in new components; fixed both. Subsequent web typecheck passed.
- pnpm lint: exit 0; pnpm test:web: 207 tests passed before new landing tests; pnpm test:contracts: 7 passed. Dedicated landing tests: 19 passed. Worker policy tests: 4 passed. See docs/landing-v1-regression-results.md for exact integration results and subsequent runs.
- Next dev 127.0.0.1:3100: agent-browser verified meaningful page and navigation, no framework error overlay, no page errors. First screenshot path failed because directory did not exist; created directory and recaptured successfully.

## Implementation files and behavior

- `apps/web/src/app/page.tsx`, root adapters, `next.config.ts`, `tsconfig.json`, and `vitest.config.ts`: compile-time profile-specific root entry; Public keeps its existing experience and excludes landing code/art.
- `apps/web/src/components/landing-v1/`: server supporting sections, client scene controller, real headings/navigation/cards/labels/dialogs, responsive CSS, strict deferred artwork, no-JS image fallback, and scene tests.
- `apps/web/src/lib/landing-v1/`: exact story data, calibrated anchors/crops, typed lookup/transition helpers and geometry tests.
- `apps/web/public/landing/floodguard-v1/`: 15 supplied WebP variants, two decorative SVGs and asset index. Reference PNGs are outside runtime output. No new dependency or artwork regeneration.
- `landing-artwork-cache.client.tsx`, `public/sw.js`, `scripts/write-offline-assets.mjs`: optional post-load artwork caching, content hashes, and Public profile exclusion. Mandatory offline app installation does not wait for story art.
- Updated root/profile/offline assertions; new worker-policy, browser-acceptance and artwork-transfer checks; local static preview helper. Original Public, Command, Studio and Python engine source behavior is preserved.

Desktop enhancement uses native scrolling and one persistent W2 image. Physical plate swaps fade through paper and reject stale image-decode callbacks. Mobile, short-height, reduced-motion, 200% text enlargement and no-JS views use natural document flow. The local observation dialog supports keyboard/Escape/focus return; the brief is a native disclosure. Activating the mobile selection scrolls its opened brief into view. No incident POST or geolocation request is part of the story.

## Final verification and delivery

All execution gates are complete. Final production browser verification finished on 15 September 2026 with 14 passed checks and zero failures, browser page errors, operational network mutations or geolocation calls. The final no-JS capture confirms that the unused source-less image placeholder is hidden while the real noscript portrait remains visible. The source-less image retains its reserved geometry; loading a real src automatically restores visibility.

| Check | Actual result | Evidence |
|---|---|---|
| `pnpm lint` / `pnpm typecheck` | Exit 0; lint without warnings, contracts/web types pass | `docs/visual-qa/landing-v1/regression/` |
| `pnpm test:web` | Exit 0; 227/227 in 37 files | `test-web-final.log` |
| `pnpm test:contracts` | Exit 0; 7/7 | `test-contracts-final.log` |
| Final targeted landing/root tests | Exit 0; 22/22 after mobile brief-scroll change | `landing-tests-final.log` |
| `node --test scripts/landing-offline-policy.test.mjs` in apps/web | Exit 0; 4/4 | `worker-policy-final.log` |
| `pnpm --filter @floodguard/web verify:profiles` | Exit 0; both exports, Public browser, same-origin cache downgrade/upgrade | `verify-profiles-before-question-fix.log` |
| Final `pnpm --filter @floodguard/web build:competition` | Exit 0; final UI, review gate off, artifact check passed | `build-competition-final.log` |
| `pnpm test:offline` | Exit 0; all four routes and 17 approved artwork files work in a primed offline browser | `offline-final.log` |
| `pnpm test:csp` | Exit 0; all four routes and existing map recovery tests under production headers | `csp-final.log` |
| `node scripts/landing-browser-smoke.mjs --base-url=http://127.0.0.1:3100 --review-gate=off --output=../../docs/visual-qa/landing-v1/browser-acceptance-production` in apps/web | Exit 0; 14/14 | `browser-acceptance-production/browser-results.json` |
| `node scripts/landing-artwork-transfer.mjs http://127.0.0.1:3100` in apps/web | Exit 0; natural post-paint worker downloads and caches all 17 assets | `browser-acceptance-production/service-worker-artwork-transfers.json` |
| Final composition capture | 54 decoded/error-free images; all nine states at all six sizes inspected | `outputs/landing-v1-review/final/captures.json` |
| `git diff --check` | Exit 0 | Final working-tree check |

Browser coverage includes native forward/reverse scroll, four real chapter anchors, direct entry/refresh/history, persistent W2 DOM image, stale-decode cancellation, OS/manual motion preferences, no-JS images/text/brief, image failure, delayed fonts, keyboard dialogs and focus return, short laptop/tablet/phones, mobile selection opening a visible brief, 200% text enlargement, and production review-gate exclusion. Test refinements and earlier failures remain documented in the browser report notes; passing functional tests alone did not substitute for screenshot inspection.

### Measured image and cache behavior

- At 1672x941, DPR1, HTTP cache disabled and service workers blocked: initial actual encoded image transfer **549,502 bytes**; only W0-1536 and the botanical decoration. Initial lab CLS was **0.00480**.
- At 390x844 under the same conditions: initial actual encoded image transfer **154,964 bytes**; only W0-768 and the botanical decoration. Initial lab CLS was **0.01225**.
- W1/W2 and portraits load later. These are measured viewport/request sets, not a guarantee that responsive upgrades never select another width.
- A separate fresh service-worker-enabled production context observed **17 worker responses totaling 3,486,287 response-body bytes**, all after first contentful paint; all were cached successfully. Body-byte measurements exclude HTTP headers and are separate from the encoded transfer measurements above.
- Public-production exports contain no landing artwork and no landing component graph. Core offline installation excludes the optional illustration set. Offline acceptance requires a prior connected visit; first-ever offline access is not claimed.

### Final artifact and local preview

- Branch `codex/landing-v1-artwork` remains at base commit `0b85f5bcd2fd0f9760df43b225ed691dcc977f5d`; changes are intentionally uncommitted. Original dirty checkouts remain preserved.
- Final Competition cache: `07cfc86e3f70`; 56 production chunks, four proposal evidence assets, 17 optional artwork assets.
- Final `apps/web/out/index.html` SHA-256: `cd8e26d56b464534e818e05b92c91387590d88588784dc007b70b39b8f1d0ad8`.
- Static preview is running at `http://127.0.0.1:3100/`, using the repository's production security headers. Restart from this worktree with `node apps/web/scripts/preview-static.mjs 3100`. To rebuild locally first, run `pnpm build:web` with the review environment flag unset.
- No push, deployment, publication, backend change or new dependency. Live API/scientific validation, field performance and owner design acceptance are outside this local implementation verification.
- Remaining aesthetic differences are documented in `docs/landing-v1-visual-review.md`: supplied clean-master framing/tone, existing font metrics, responsive reflow, finite source resolution, faint paper edge and preserved PWA badge. No critical settled-scene visual defect remains in the inspected matrix.

An agent-created duplicate calibration PNG remains at `C:\Users\iputu\AppData\Local\CodexWorktrees\flood-guard\outputs\landing-v1-review\calibration\w0-clinic-seed.png`. Automatic approval review rejected its deletion with “blocked by policy”; it was left in place. This does not affect the application or export.

## Paused by user — 2026-09-15

User explicitly requested pausing development. All active implementation/review agents were interrupted and the restarted Next dev preview was stopped. Changes and review artifacts are preserved; no push or deployment.

Resume from this worktree, not the stale Documents checkout. Completed before pause: full stable development browser suite 14/14; initial image bytes 547,904 desktop /153,366 mobile with HTTP cache disabled and service worker blocked; 200% text enlargement passed; earlier Public and Competition profile builds/artifact/browser cache transitions passed. See browser-acceptance-final/browser-results.json and verify-profiles-before-final-style.log for exact tested versions.

At the pause, the 1100–1599px typography/card spacing refinement and hero clinic-label offset were not yet verified. The user's subsequent “continue” instruction resumed the task. Those changes and later visual/fallback fixes have now been recaptured, rebuilt and verified as recorded in the final section above.
