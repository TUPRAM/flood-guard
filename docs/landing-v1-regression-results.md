# FloodGuard landing v1 regression results

Verified locally on 15 September 2026 in `C:\Users\iputu\AppData\Local\CodexWorktrees\flood-guard\landing-v1`.
Base: `0b85f5bcd2fd0f9760df43b225ed691dcc977f5d`; branch: `codex/landing-v1-artwork`.
No push or deployment. This report covers technical regression checks. The visual report and owner design acceptance are separate.

## Final command results

All commands below completed with exit 0. Commands ran from the repository root. Logs are under `docs/visual-qa/landing-v1/regression/`.

| Command | Actual result | Log |
| --- | --- | --- |
| `pnpm lint` | PASS, ESLint with zero permitted warnings; rerun after the final CSS and brief-scroll change | `lint-final.log` |
| `pnpm typecheck` | PASS, contracts and web; rerun against the final production build | `typecheck-final.log` |
| `pnpm test:web` | PASS, 37 files and 227 tests; 15.33 s Vitest duration | `test-web-final.log` |
| `pnpm test:contracts` | PASS, 1 file and 7 tests; 5.92 s Vitest duration | `test-contracts-final.log` |
| `pnpm --filter @floodguard/web exec vitest run src/components/landing-v1/scene-frame.test.tsx src/lib/landing-v1/story.test.ts src/app/page.test.tsx --configLoader runner` | PASS, 3 files and 22 tests; rerun after the final brief-scroll change | `landing-tests-final.log` |
| `node --test apps/web/scripts/landing-offline-policy.test.mjs` | PASS, 4 tests | `worker-policy-final.log` |
| `pnpm --filter @floodguard/web verify:profiles` | PASS, both static builds, artifact checks, direct Public browser check and same-origin profile transitions | `verify-profiles-before-question-fix.log` |
| `pnpm --filter @floodguard/web build:competition` | PASS, final UI built with review mode disabled; static artifact check also passed | `build-competition-final.log` |
| `pnpm test:offline` | PASS, static inventory and real browser offline checks | `offline-final.log` |
| `pnpm test:csp` | PASS, all four application routes under the repository's production security headers | `csp-final.log` |
| `git diff --check` | PASS after final build; no whitespace errors | Empty output, exit 0 |
| `node --check apps/web/scripts/preview-static.mjs` | PASS | Empty output, exit 0 |

The full web suite includes 20 new landing tests (11 server-rendered scene tests and 9 story/geometry tests), two root-entry tests, and the existing application tests. The final refinements after that full run were local CSS constraints and scrolling an opened brief into view. The affected landing/root tests were rerun and passed 22/22. No test was disabled or weakened to hide a failure.

The browser acceptance owner also verified syntax and targeted ESLint for `landing-browser-smoke.mjs` and `landing-artwork-transfer.mjs`. The subsequent complete lint run includes both scripts.

## Profiles and final artifact

The complete profile verification used the final profile/cache policy and passed:

- **Public-production:** direct Public entry, five-page Public navigation, absent staff routes and excluded staff/evidence/artwork payloads, normalized offline navigation and cache inventory. The build contained 47 production chunks, 0 proposal evidence assets and 0 deferred illustration assets; cache `2397c68db856`.
- **Competition:** Landing, Public, Command and Studio routes; source/qualification boundaries, artifact inventory and optional artwork policy.
- **Actual same-origin profile changes:** competition-to-Public downgrade purged competition content and artwork; Public-to-competition required the established user update flow; offline staff readiness and reconnect state passed.

After that profile run, the remaining UI changes constrained the S3A question, adjusted captions/mobile report-label spacing, scrolled the native brief into view on activation, and hid source-less deferred image elements so that they cannot paint a broken-image rectangle over the no-JavaScript fallback. These did not change the Public entry graph or profile/cache policy. A final competition build was therefore run after those changes, followed by offline and CSP browser checks against that exact export.

Final competition export:

- `apps/web/out/`, profile `competition`, entry `/`.
- Routes: `/`, `/public/`, `/command/`, `/studio/` and the framework not-found route.
- 56 production chunks, 4 proposal evidence assets and 17 optional illustration assets.
- Content-derived cache: `07cfc86e3f70`.
- Root HTML SHA-256: `cd8e26d56b464534e818e05b92c91387590d88588784dc007b70b39b8f1d0ad8`.
- `NEXT_PUBLIC_FLOODGUARD_LANDING_REVIEW` cleared for the build.
- `next-env.d.ts` returned to its tracked production form; no generated-file diff remains.
- Static export, trailing slashes and unoptimized image behavior remain in place.

The older `verify-profiles-before-final-style.log` is retained as earlier regression evidence. Build, offline and CSP logs from immediately before the no-JavaScript image fix are preserved with a `-before-noscript-fix.log` suffix. These earlier logs are not presented as checks of the final UI.

## Offline acceptance

`pnpm test:offline` verified:

1. Four exported routes and 15 required core assets pass the static inventory checks.
2. A fresh browser installs the content-versioned worker and primes the application cache.
3. The landing's post-paint request caches all 17 approved illustration assets. With networking disabled, every approved width variant remains fetchable with a nonempty response.
4. Landing, Public, Command and Studio render from the saved cache. Public navigation, planning-area controls, household preparation flow, Command evidence/ranking and Studio content preserve their existing checks.
5. Approved basemap requests fail gracefully; no unapproved external request is introduced.
6. The legacy dashboard's embedded Leaflet vectors, text equivalent and dataset controls work offline.

This proves primed-cache behavior. First-ever offline access is not claimed. Artwork transfer measurements are recorded separately by the production browser/transfer harness; inventory counts are not substituted for network measurements.

### Worker policy tests

The four tests execute the real service-worker source inside a controlled worker harness:

- Core installation does not fetch illustration assets; a later explicit request caches approved art and reuses it.
- A response with the wrong SHA-256 remains uncached while core application files stay available.
- A new content-versioned worker removes old art and accepts the updated expected hash.
- A Public downgrade excludes artwork; an in-flight response cannot revive the old competition cache.

These focused policy tests complement the actual browser installation/offline and profile-transition checks.

## CSP acceptance

`pnpm test:csp` served the final export with the actual global headers from `vercel.json`. All four routes rendered without a CSP failure. The existing Public/map regressions also passed: address selection, opt-in synthetic GPS, provider 403 error images, partial loads, timeout, retry, hide/show, provider switching, offline behavior and origin-only referrers.

External map/address services are controlled fixtures in this test. This is local browser verification of the configured policy, not a production network or deployment claim.

## Scope and verification boundaries

Separate production-browser evidence is written to:

- [Landing interaction and fallback results](visual-qa/landing-v1/browser-acceptance-production/browser-results.json).
- [Actual service-worker artwork transfers](visual-qa/landing-v1/browser-acceptance-production/service-worker-artwork-transfers.json).

Those harnesses run against the final static preview with the review gate disabled. Their recorded statuses and measurements govern their results; this regression report does not infer a pass from the profile/offline/CSP checks.

- The final production landing interaction and screenshot matrix, no-JavaScript/reduced-motion behavior, image/font failure handling, keyboard tests and measured artwork transfers are reported by the landing browser harness and visual-review outputs.
- Package integrity/helper tests are documented in the execution record; they are not counted as website integration tests.
- Python flood detection, scoring, equity/access calculations and live API behavior were unchanged. Their separate scientific/live-service suites were not run for this UI task.
- No load/FPS benchmark, field Core Web Vitals measurement or owner design sign-off is claimed.
- The early missing-module root test occurred while its component was being authored; completing that module resolved it. Subsequent root and full web suites passed.
