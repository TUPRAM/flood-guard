# Landing V4 Acceptance Tests

Initial protocol, September 12, 2026. Results must be appended against a
specific source/artifact snapshot after implementation. A protocol is not a
pass, and a local technical pass is not a human, scientific, agency, or
production approval. No formative user test has been performed by this work.

## Scope And Stage Evidence

The approved implementation scope is a four-chapter core demonstration:
`place`, `flood`, `access`, and `finding`, followed by distinct unpinned
workspaces and historical evidence sections. The shortened story replaces
the previous eight-role animation; older eight-chapter, hero-copy, and
mobile-pixel expectations are not the V4 acceptance oracle.

| Stage | Required evidence | Initial status |
| --- | --- | --- |
| 1: Claims | Current-route/source audit and `positioning-and-claims.md` | Local audit complete; no external approval claimed |
| 2: Static storyboard | Connected neighborhood, flood evidence, access consequence, explainable finding, actual workspace views, historical evidence | Pending final authored frames and internal review |
| 3: Finished visual system | Hero, access, and finding frames reviewed at target widths; typography, geometry, materials, labels, and contrast | Pending final candidates |
| 4: Reusable implementation | Stable scene/data IDs, one state model, same connection through geographic/map views, separate synthetic/historical sources | Pending final code and focused unit tests |
| 5: Integration | Actual route destinations, final production browser matrix, resource/performance evidence, static and failure cases | Pending final export |

Use `landing-storyboard.md`, `visual-system.md`, the scene manifest, and the
claim matrix together. A beautiful isolated frame cannot replace testing the
transition or the destination it advertises.

## Story And Claim Checks

| ID | Test | Required result |
| --- | --- | --- |
| CLAIM-01 | Read the hero without scrolling or animation | Flood evidence, possible loss of access, and planning purpose are concrete; historical prototype/not-live-service status and direct workspace actions are visible |
| CLAIM-02 | Freeze the first scene | Homes, an essential facility, and their connection are identifiable; anonymous aerial context alone is insufficient |
| CLAIM-03 | Compare `place` and `flood` | The same home/facility/link remain identifiable. Flood evidence is distinct from a confirmed road closure |
| CLAIM-04 | Inspect `access` | Explicit text/symbol identifies the assumed disrupted link and the modelled consequence; the chosen dry home remains outside the illustrated footprint |
| CLAIM-05 | Inspect `finding` | A compact finding, its reason, its uncertainty, and a reviewable next step are all present. The synthetic label is adjacent, with no invented Mae Sai quantities |
| CLAIM-06 | Inspect workspace section | Public shows an actual preparedness task; Planning shows an actual area/result/limitation; Studio shows actual source/evaluation/authorization evidence. They are not portrayed as one consecutive live incident workflow |
| CLAIM-07 | Follow every primary/secondary CTA | Destination exists and offers the advertised task. No invented `/public/prepare`, inactive-tab hash, historical scenario editor, or fabricated area/result URL |
| CLAIM-08 | Read case evidence | Available / Derived / Needs verification are distinct; February optical context is not labelled as September flood imagery; canonical qualified evaluation and operational authorization remain absent |
| CLAIM-09 | Compare historical and illustrated data | Synthetic IDs/results do not overwrite, extend, or masquerade as the canonical Mae Sai bundle. No GeoAI research metric is promoted into the canonical Studio context |
| CLAIM-10 | Scan every label and FAQ | No official-warning, live-safe-route, capacity-aware allocation, verified current facility/road status, universal deployment, superiority, agency acceptance, or proven-impact claim is introduced |

This checklist is a structured local comprehension review, not evidence that
unfamiliar visitors understood the page. The supplied review's proposed
formative questions should be used later with actual participants and their
responses recorded; no participant result may be invented.

## Scene And Motion Checks

- Record the final manifest IDs for household origin, essential facility, relevant road link, and baseline/interrupted paths. Assert identity and world coordinates stay stable throughout the sequence and reverse scrolling.
- Compare dry/flood/access registration at the required held camera states. Record camera signature and projected landmark positions rather than relying only on visually similar screenshots.
- Water state, access state, and priority annotations are separate variables. Water color alone cannot imply closure or safety.
- An assumed disruption must change the highlighted network state and a visible consequence. Merely recoloring streets or changing the caption does not satisfy the demonstration.
- Maintain one mounted story renderer/canvas. Verify nonblank pixels, object framing, correct scene state after direct seeks, and no unintended renderer remount on chapter changes.
- Drive smooth forward scrolling and save an actual browser recording plus sampled progress. Also test rapid jumps, reverse through every boundary, and direct loading of each chapter hash.
- Keep the text reading position stable while a core network transformation occurs. Do not animate camera, text position, page geometry, and multiple competing callouts simultaneously.
- Check partial transitions, not only endpoints: no poster/canvas blank frame, unrelated-place jump, stale flood state, duplicated label, or contradictory navigation state.
- Verify offscreen, hidden-document, and motion-disabled rendering becomes idle after a bounded settling period. A continuously rendering loop must fail a bounded timeout; do not hide it by increasing wait durations.
- Test resize desktop -> compact -> desktop at an intermediate state. Preserve meaningful position, recompute layout/registration, and avoid multiple renderers or reset-to-unrelated-chapter behavior.

## Accessibility And Layout

| Surface | Required checks |
| --- | --- |
| Desktop | At least 1366x768, 1440x900, 1920x1080, 2048x1152; headline, source labels, scene, and next-section cue fit without overlap |
| Compact/short | 1024x768 and 1264x620; readable content and deliberate static/compact policy, not a clipped desktop scene |
| Mobile | 390x844 and 320x768; stacked complete diagrams, all four concepts and actions, no horizontal overflow or missing qualifications |
| Header | Constant clear zone for chapter anchors, keyboard focus, menus, and skip destinations; test expanded menus as well as closed state |
| Chapter controls | Meaningful names rather than anonymous numbers alone; current state announced; mobile current-name/previous/next controls if implemented; no hidden focus trap |
| Motion controls | Icon-only Reduce motion / Enable motion retains all concepts/actions and preserves reading position. This preference is per visit, not persisted. Skip to workspaces is separate. OS reduced motion and automatic fallback policies cannot be overridden |
| Semantics | Headings and landmarks are coherent; buttons/links have matching visible accessible names; focus remains visible; controls do not depend on color alone |
| Automatic checks | Axe WCAG 2A/2AA/2.1AA/2.2AA at representative desktop/mobile states; record violations and incomplete results separately |
| Manual checks | Evaluate bitmap-backed text contrast and scene callouts at actual frames; inspect keyboard order, focus geometry, and PWA status-band overlap. Date and hash-bind the review |

Incomplete automated contrast results are not passes. A solid-background
calculation does not establish the minimum contrast over every bitmap pixel.
Use source/computed colors plus rendered backing samples for the text regions
actually reviewed, and state the limits of that review.

## Fallbacks And Resource Targets

Test JavaScript disabled, reduced-motion preference, save-data policy,
unavailable WebGL, renderer chunk failure, image failure, and offline state.
In each supported fallback, the normal page must contain the complete
argument, readable static diagrams/product views, source limitations, and
working navigation. No-JavaScript content must not require a canvas.

Initial targets retain the previous desktop enhancement budget until the
implementation owner explicitly revises the scope before measurement:

- Initial transferred bytes, including navigation document, poster, fonts, and any initially requested renderer: at most 2 MiB.
- Full tested story plus product/evidence sections: at most 3 MiB transferred. Count requests caused by lazy imagery and optional renderer loading, and report SW precache separately.
- At most 250,000 visible triangles and 45 draw calls in the tested scene; record actual counts, not just a boolean pass.
- Cumulative layout shift at most 0.1 for initial load and the full tested story; retain shift-source traces for any failure.
- Record measured LCP, initial/full transferred bytes, renderer identity/driver, and frame-time distribution for the actual scrolling run. No universal FPS or field-performance claim from a local browser sample.

Measure against a production export with one declared browser/driver and no
concurrent heavy GPU tasks. Preserve failed measurements and their cause.
Do not compare image baselines across different browser versions, viewport
sizes, or development/production PWA environments and call the result an
application regression. No threshold may be relaxed after seeing failure
without a source-backed correction to the test oracle or an explicit scope
decision documented separately.

## Product And Operational Boundaries

- Publish only the inspected real UI crops and a manifest recording route, viewport, UI state, capture date, source hashes, processing, and qualifications.
- The landing-specific browser harness and product-capture audit do not create household information, location, observation, report, task assignment, acknowledgment, or operational authorization.
- The separate pre-existing offline browser smoke intentionally creates fixture report, household-needs, and checklist state in a disposable Playwright context's local storage, then reloads to verify persistence. These are isolated device-local test fixtures, not a real household, the user's browser profile, external submissions, or operational authorization. Do not generalize the landing harness's no-write result to mean that no test fixture was created anywhere.
- Watch all request methods and geolocation calls. Read-only basemap requests may occur only in actual product-route checks and must be attributed separately from strict landing network checks.
- Preserve the existing eight-cycle Public/landing navigation regression, waiting for a visible Leaflet overlay canvas before each return, with short variable dwell times. Browser exceptions must not be filtered away.
- Retest Public/competition export isolation, same-origin cache transitions, offline routes, and CSP using the existing repository checks. Optional landing images/renderers must not become mandatory Public precache assets.
- Recheck actual destination state after final export, not only the development screenshots. No claim that the page deploys or changes live operational behavior follows from a local pass.

## Result Record

Append the final artifact/cache identifier, source hashes, command list,
test counts, browser/driver versions, screenshot/video paths, performance
figures, failed/revised checks, residual risks, and every not-run boundary.
Keep raw evidence immutable; add an explicit receipt when multiple valid
browser/environment runs jointly satisfy the protocol.

The initial protocol preceded implementation. The final local result is
recorded below; the intervening diagnostics remain historical evidence,
not the current acceptance status.

## Initial Integration Findings

The reusable script is `apps/web/scripts/landing-v4-smoke.mjs`. It accepts
named case filters, `FLOODGUARD_V4_URL` for an existing server,
`FLOODGUARD_V4_OUT` for a production export served locally with repository
CSP and gzip, and `FLOODGUARD_V4_EVIDENCE` for a fresh evidence directory.
It never builds, deploys, or changes product records. Production transfer
budgets are not enforced against development bundles.

September 12 local development checks at 1366x768, cold `#finding`, and
390x844 passed 3/3 after these defects were corrected:

- The finding clock previously continued after its sticky stage released,
  putting the finding under the header. A trailing story hold now keeps the
  stage pinned through the finding. The original failure remains in
  `test-results/landing-v4/initial-desktop-3`.
- Unprojected annotations could appear before a renderer frame. Readiness now
  starts false until actual projected coordinates are available. Delayed
  renderer cases are included in the final matrix.
- Product alternative text mentioned a nonexistent meeting-point field and
  ambiguously called modelled summaries qualified results. Both descriptions
  were corrected to match their actual captured views.

The passing initial subset is recorded in
`test-results/landing-v4/initial-fixed/landing-v4-smoke.json`. Camera and
landmark identity held across all four close states. Isolated canvas pixels,
with HTML overlays temporarily hidden only during those comparison captures,
changed by 1.1329% for water and 0.1045% for network disruption. Ordinary
screenshots and the motion recording retain all UI. Axe found zero violations
in the two assessed states; its 35 desktop and 9 mobile contrast-incomplete
nodes are not passes and still require final manual review.

The first production export, cache `floodguard-offline-6ed927e3a442`, failed
the production-only availability/chapter-controls overlap check by 1318.875
square pixels. That failure is retained in
`test-results/landing-v4/production-initial`. Initial transfer was 2,015,427
bytes including navigation, initial CLS was 0.004999, and local LCP was
644 ms on Chrome 152 / NVIDIA RTX 3060. The full story was deliberately not
accepted after that geometry failure. These are historical diagnostic
measurements, not final artifact acceptance or field performance.

September 13 diagnostic follow-up on cache `floodguard-offline-f1d7cff08d31`
completed 20 of 24 cases successfully. Its four failures were retained and
classified rather than suppressed:

- Reloading after per-visit motion reduction restored the longer static
  page's scroll offset before desktop compaction. Explicit Reduce/Enable
  itself passed. Initial hydration now captures the semantic reading
  position and restores it after the new clock measures; focused development
  reload/resize checks passed afterward.
- The new rapid cross-workspace history test exposed a real mixed-navigation
  race: a second Back before Planning installed its router listener changed
  the URL to `/` while retaining Planning's SSR document. The independent
  held-hydration trace records the listener being absent when the event fired,
  and the wrong document remaining after 20 seconds. Landing workspace links
  were changed to native document links, matching the destinations. The final
  suite retains rapid Back and adds an explicit held-script regression; no
  hydration-wait workaround was added.
- Native fragment navigation correctly made `body` the active element after
  Enter on a nonfocusable section. The old test incorrectly required that
  body's full document rectangle fit the viewport. The corrected oracle
  checks visible focus before Enter and the actual next Tab target afterward.
- A direct `#access` load sampled the start of network interruption, with
  network progress 0.19974. The old test incorrectly required the affected
  link label's opacity to equal its final state. It now checks exact sampled
  opacity; complete endpoint tests still require the full network state.

Raw evidence is in `production-final`, `focused-diagnostics`, and the
independent `native-history-api-diagnostic` directories under
`apps/web/test-results/landing-v4`. The six-case development restoration and
fault-policy subset passed in `dev-restoration-check`. The headless browser
does not provide native hidden-tab behavior when switching tabs, so its
hidden-document test explicitly simulates the visibility policy, verifies a
bounded idle frame count, and does not claim native background scheduling.

The final automated matrix has 29 cases. Separate explicitly selected
`manual-contrast-1366`, `manual-contrast-390`, and `motion-review` modes produce
the review evidence. The clean motion recording does not run the temporary
HTML/text-hiding screenshot operations used by pixel and contrast checks.
Rendered backing measurements cover actual visible text-line rectangles;
closed-details content and boxless `display: contents` ancestors are handled
explicitly. A dated manual record must identify reviewed frames, regions,
source hashes, and the production export rather than treating an old review
as an automatic pass for future CSS.

The subsequent `fa05682456cb` production matrix retained 27 passing cases
and two navigation-oracle failures in `production-accepted`. Navigation and
the held-hydration Back behavior completed correctly; the raw failures were
GET requests canceled when their owning document was abandoned. A request
epoch alone was insufficient because Chromium can deliver `ERR_ABORTED`
before the next document request. The corrected oracle records each actual
click/Back intent, the source document UUID and request epoch, and a confirmed
different destination document. Only an abort belonging to that source and
departure interval is classified as navigation cancellation. Active-document
failures, JavaScript errors, unexpected hosts, and operational writes remain
failures. This instrumentation adds no hydration wait or navigation dwell.

The separate `production-review` record exposed an additional real desktop
reading collision: the centered floating availability pill covered part of
a FAQ question. The desktop/tablet control now follows the footer in document
flow; the existing compact opaque bottom band remains unchanged. The final
matrix must verify the in-flow control can be opened and closed and that its
content is reachable. The old collision screenshot remains preserved.

The same pixel investigation identified a contrast-oracle distinction:
text below an opaque fixed status band is not visible text backed by that
band's teal icon. The collector now records foreign fixed/sticky occlusion
rectangles and their excluded pixel counts separately. Completely occluded
text is unmeasured, not a contrast pass. Manual review still evaluates
partial-line collisions, scrolling reachability, and the normal screenshots.
No contrast threshold was reduced.

## Final Local Result: September 13, 2026

The five requested implementation stages are complete locally: the claims
matrix, six-frame storyboard, visual system, four-chapter working experience
with generated assets and actual product previews, and scoped acceptance
evidence. This is not human design approval, a formative comprehension study,
scientific validation, agency acceptance, deployment, or operational release.

The final production export is
`floodguard-offline-717f35448e7e`. The portable machine-readable record is
`apps/web/test-results/landing-v4/acceptance-receipt.json`; the dated manual
record is `manual-review-2026-09-13.json` in the same directory. Both bind
the actual artifact, application source, fonts/license, scene and product
manifests, raw report versions, and referenced images. The raw reports retain
their original absolute paths and hashes; the receipt uses portable paths
relative to `landing-v4`.

| Evidence | Result and qualification |
| --- | --- |
| `production-release/landing-v4-smoke.json` | Raw FAIL, 27/29 passing. All non-navigation cases pass. Both navigation behaviors completed, but the request-start epoch oracle misattributed late outgoing lazy-image aborts. This raw result was not relabelled. |
| `release-review/landing-v4-smoke.json` | Both navigation regressions PASS with committed-document ownership proof. Clean motion PASS. Raw overall FAIL, 4/5, because the older desktop contrast collector mistook the sticky stage behind the hero for a foreground occluder. |
| `release-manual/landing-v4-smoke.json` | Final scoped rendered-backing measurement, PASS 2/2. Foreground exclusion uses actual hit-testing, not rectangle overlap alone. |
| Composite browser acceptance | PASS for 29 distinct required cases: 27 unchanged main cases plus two focused navigation cases, on the identical application/export. Only the QA oracle changed between reports. |
| Repository checks | 241 web tests in 37 files; full ESLint with zero warnings; TypeScript; Public and competition builds; Public browser isolation; bidirectional same-origin cache transitions: PASS. |
| Offline and CSP | Offline artifact: four routes and 15 core assets. Browser offline: four routes from versioned SW cache plus legacy dashboard vectors. Production-header CSP: four routes. PASS on the final export. |

The final Public profile is `floodguard-offline-add79a688802`. Root-run logs
are retained as `profile-verification-release.log`, `unit-tests-release.log`,
`lint-release.log`, `offline-browser-release.log`, and `csp-release.log` under
the V4 evidence directory. The earlier offline-browser failure caused by old
V3 copy assertions remains in `offline-browser-accepted.log`.

### Browser Coverage

The main matrix covers 1366x768, 1920x1080, 1100x700, 1440x900 and 2048x1152;
four cold fragment entries; reverse and direct jumps; pointer reset; resizing;
per-visit Reduce/Enable, native reload and pending-restoration hash changes;
keyboard Enter/Space, visible focus, menu Escape, FAQ and scrollbar behavior;
390x844, 320x768, 1024x768 and 1264x620 static views; reduced motion,
JavaScript disabled, unavailable WebGL, save-data and offline policies;
delayed renderer, renderer/image failure, intentional mounted-context loss,
and bounded idle behavior. Products, source qualifications, viewport overflow,
PWA open/closed/footer reachability, one actual canvas identity, registered
camera/landmarks, changed water/network pixels and persistent final water
are checked rather than inferred from a build.

The final lifecycle regression exercises eight actual Public Leaflet canvases,
eight Planning visits and eight Studio visits, using zero, 60 or 200 ms dwell
after the Public canvas is visible. The controlled Back regression holds real
Planning scripts, verifies zero router listeners, and returns to a new landing
document before releasing hydration. No extra hydration wait was introduced.
Native document navigation may use BFCache; these results do not guarantee
React unmount or GPU disposal on every departure.

Unexpected active-document asset failures, browser exceptions, forbidden
hosts, geolocation and operational writes remain strict failures. Same-origin
GET aborts are excluded only with an exact committed source-document epoch,
source URL, UUID-confirmed destination change and departure interval. Approved
OSM/ArcGIS basemap requests during actual workspace transitions are recorded
separately; their availability is not a landing dependency or a claim that
every external map tile loaded during rapid departure.

### Measured Quality

The local production sample used Chrome 152.0.7977.83 and the NVIDIA GeForce
RTX 3060 Laptop GPU through ANGLE/D3D11. No other heavy browser task ran during
the recorded performance sample.

| Metric | Actual result | Unchanged limit |
| --- | --- | --- |
| Initial transferred bytes, including document | 1,452,076 bytes | 2 MiB |
| Full story, products and evidence transfer | 2,565,901 bytes | 3 MiB |
| Initial / full accumulated layout shift | 0 / 0.0017316 | 0.1 |
| Local LCP | 476 ms | Recorded, not a field claim |
| Maximum scene triangles / draw calls | 230,474 / 27 | 250,000 / 45 |
| Axe WCAG 2A/AA, 2.1AA, 2.2AA | Zero violations in assessed desktop/mobile states | Incomplete results retained |

Axe reported color-contrast incomplete results for 38 desktop and nine mobile
nodes. These were not globally marked passed. The separate dated review
inspected 14 actual frames and measured 191 unobscured text runs. The minimum
was 5.1496:1 for the 10px orange access qualification (`#9a4309`) over its
darkest sampled backing pixel, RGB 222,228,233. Hero supporting copy measured
at least 6.3256:1; finding qualification 5.8695:1; historical case-caption
qualification 5.7142:1. Normal text still requires 4.5:1 and large text 3:1.
Five wholly occluded mobile text runs beneath the opaque status band are
explicitly unmeasured, not contrast passes. There is no claim about every
scroll position or text rendered inside captured product screenshots.

The clean actual scroll video is retained in `release-review/recordings`,
with 18 extracted frames and a contact sheet in
`release-review/motion-review-frames`. The 26.4-second recording shows opening,
connection, flood, assumed disruption, finding and reverse travel in the same
registered neighborhood. Its zero-second blank is pre-navigation browser
recording, not a story frame. The seven measured scroll legs contain 2,366 RAF
intervals, median gaps about 6.1 ms and per-leg p95 gaps 6.2-12.1 ms. One gap
exceeds 50 ms, at 139.5 ms, and is retained. These are local input/RAF timing
observations, not a universal FPS, GPU frame-time or field-performance claim.

### Reproduction

From the worktree's `apps/web`, after a production competition export exists:

```powershell
$env:FLOODGUARD_BROWSER_EXECUTABLE = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
$env:FLOODGUARD_V4_OUT = 'out'
$env:FLOODGUARD_V4_EVIDENCE = 'test-results/landing-v4/fresh-main-run'
node scripts/landing-v4-smoke.mjs
$env:FLOODGUARD_V4_EVIDENCE = 'test-results/landing-v4/fresh-review-run'
node scripts/landing-v4-smoke.mjs motion-review manual-contrast-1366 manual-contrast-390
```

Named filters also reproduce `route-lifecycle` and
`native-history-before-hydration` without rerunning the other cases. Fresh
results must retain their own statuses and require a new dated manual review;
the September 13 receipt does not automatically accept changed sources.

The scene remains a controlled synthetic explanation. The real Mae Sai
candidate still has unresolved reference evaluation, facility operation,
segment-level flood intersection and agency acceptance; the pre-existing
conflicting separate GeoAI summary is documented in the claim matrix, not
fixed or promoted by this landing work. No live report submission, deployment,
real-household test, human comprehension study or operational authorization
was performed. The separate offline harness's disposable local fixtures are
described in the operational boundaries above.
