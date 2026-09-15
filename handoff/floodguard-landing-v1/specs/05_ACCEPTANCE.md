# Acceptance and visual review

## Two separate questions

Functional regression asks whether the implementation works and preserves the app. Visual review asks whether it resembles the supplied target and explains the story. Passing one does not prove the other. Self-generated screenshot baselines cannot certify that a wrong first implementation matches the target.

## Required visual inspection

Before implementation, inspect original H-01, S1-01, S3A-01, and S3B-01 at native resolution, then the remaining desktop/mobile references and all reusable art. After implementation, capture the same states at 1672×941 and compare the browser render to the source. Also test 1920×1080, 1440×900, 1024×768, 390×844, and 360×800. Mobile scenes may legitimately exceed a viewport; no forced unreadable scaling.

Create side-by-side review sheets or use the included workbench and actual capture files. Inspect the top three mismatches, fix them, recapture. Do at least two real capture/inspection rounds when tooling is available; do not claim that the number of rounds alone means aesthetic success. Keep comments and unresolved differences.

Do not use a rigid full-image similarity percentage across separately generated reference scenes to prove fidelity. The reference clean plate is not exactly the same geometry/framing as every composite, and browser typography differs from raster text. Use references as visual targets, semantic regions as checks, and pixel snapshots for regression after an accepted implementation baseline exists.

## Visual failure conditions

- Replacing the provided art with a generic low-poly or random town.
- Serving the complete reference PNG as a screen, hiding important text in raster, or placing invisible hotspots over baked buttons.
- Full-width opaque water planes, deforming buildings, long ghosted W0/W1/W2 dissolves, or changing the W2 footprint during the solution.
- Home/clinic/connection clipped, blocked by cards, swapped, or relabeled; route endpoint on a roof; route through a garden due to independent crop math.
- Huge tiny-text cards, duplicated portraits, floating torso cutouts, alpha loss, obvious portrait edge halos on the chosen paper, oversized empty rails, or generic placeholder icons.
- Small laptop nav collisions, headings under the fixed header, horizontal overflow, inactive transparent buttons receiving focus.
- False confidence: measured-looking invented percentages/closures, live source times, verified DEMO-R01, official dispatch, safe navigation, or an all-clear ending.

## Per-scene visual gates

| Frame | Must be visible | Must not appear |
|---|---|---|
| H-01 | Two-line promise, usable CTAs, detailed W0 town, no portrait | App loading curtain, unexplained empty map, storm |
| S1-01 | Gate-to-clinic connection, two dry endpoints, resident/card | Shelter substitution, game-like traffic loop |
| S2-01 | W1 water increase, unchanged view, dry low road, preparedness card | Forecast probability, lightning theatre, fake authority |
| S3A-01 | Dry home and clinic, affected illustrated link, resident question | Full isolation claim, green safe reroute |
| S3B-OBS | Hollow sample pin, DEMO-R01, Not verified | Real submission or received/dispatch confirmation |
| S3B-01 | Exact W2, planner, selected area, basis/local input/review needs | Arbitrary risk score or fake flood-polygon measurement |
| S4-01 | Review brief, reason, next check, unknown clinic status | Agency completion badge |
| S4-PUBLIC | Resident, simpler preparedness, real relevant links | Staff route exported into a live navigation instruction |
| S4-END | Flood remains, clear next step, role links, limits | Water magically gone, celebratory rescue, all clear |

## Functional browser checks

Hero and role links work immediately, without completing the story. Chapter links are real anchors; direct entry/refresh at a chapter works. Forward/back scrolling does not leave wrong labels on a plate. Every frame ID resolves deterministically; microstates stay in the correct chapter. No stale decode callback overwrites the current scene. Current navigation indication matches the same state object as text and art.

The sample observation and brief are keyboard-inspectable local examples. Any dialog closes on Escape, returns focus, has a correct accessible name, and does not obscure the status. No demo interaction makes an incident API POST or asks for location permission. External contact links use existing verified app data.

Test 200% text zoom, keyboard-only operation, prefers-reduced-motion from initial load, changing the preference while reading, the manual preference control, no JavaScript, image failure, font delay, browser back/forward, and a short-height laptop. Tab order excludes inactive duplicates. No live region repeatedly announces scrolling.

## Preserved project checks

Run the actual app lint/typecheck/unit tests and profile builds. Public/Command/Studio still work. Public-production root and excluded routes/payloads follow existing policy. Old landing-scene code is not downloaded unnecessarily if it was replaced; do not delete shared code until references are checked. CSP violations are absent. Static deployment makes no request to the unsupported Next image optimizer. No new sensitive data cache or weakened authorization is introduced.

Offline: demonstrate the strategy with a primed service worker/cache, then disable network. Navigation and meaningful text still work; approved cached artwork resolves or a clear textual fallback appears. This is not a promise of first-ever offline access. Check art hash changes update the cache and that public-production does not inherit the competition asset set.

## Performance evidence

Measure actual image requests and transferred bytes, not only disk sizes. Confirm only one srcset variant per active asset in normal use, aside from legitimate responsive upgrades. Record lazy/deferred loads and SW precache transfers separately. Confirm width/height reservation prevents artwork-driven layout shifts. Record device/viewport/cache state for measurements. FPS, Lighthouse, and Core Web Vitals targets are targets until actually measured; do not fabricate a passing number or claim lab timing proves field performance.

## Toolkit versus website validation

The included helper tests cover coordinate transforms, geometry input validation, scene lookup, and transition rules. They do not test React integration, SVG label collision, actual road alignment, accessibility, visual similarity, or the project build. The report from this package must not be copied into the implementation report as proof of website testing.

## Completion report template

Include: baseline branch/working tree; actual changed files; rendering choice; source assets and derived files used; route/crop calibration changes; all command results with exit status; browser viewports and capture paths; visual differences fixed; remaining differences; performance/cache observations; unavailable tools; no push/deployment statement. Owner design acceptance remains separate from agent self-review.
