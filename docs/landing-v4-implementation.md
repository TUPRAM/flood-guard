# FloodGuard Landing V4

Implementation of the supplied review's five stages in the existing isolated
landing worktree. This supersedes the V3 eight-chapter presentation, not the
historical geospatial analysis, Public application, or evidence-governance
contracts. No deployment or operational mutation is part of this change.

## Deliverables

1. [Positioning and claims](positioning-and-claims.md): source-backed maturity matrix, actual destinations, historical source dates, and unsupported claims.
2. [Static storyboard](landing-storyboard.md): six essential conceptual frames and a four-chapter animated story.
3. [Visual system](visual-system.md): Public identity, free Instrument Sans, registered scene annotations, physical water versus analytical assumptions, and real product imagery.
4. [Scene manifest](../apps/web/public/landing/desktop-v4/scene-manifest.json): five same-master frames, source and asset hashes, camera/anchor registration, graph assumptions, and render counts.
5. [Acceptance tests](acceptance-tests.md): local browser, accessibility, source, fallback, profile, offline, and runtime evidence with limits stated separately.

## Changed Experience

The hero positions FloodGuard as a historical planning prototype and offers
immediate Planning entry. A wide authored town moves into one recognizable
connection. Four chapters explain the baseline, illustrative flood overlap,
an explicitly assumed link disruption, and a finding with its reason,
uncertainty, and reviewable next step.

The synthetic graph is separate from the historical bundle. Removing its
identified crossing changes reachability; flood overlap itself never removes
an edge. Surrounding roads are context, not a complete transport graph. No
real population, travel time, capacity, priority score, or verified road
closure is invented for the animation.

Ordinary document sections then show the method, three distinct actual
product captures, and a historical evidence inventory: Available, Derived,
Needs verification. Scenario editing is not promised by the Planning CTA.
The old sample-report receipt/task-assignment sequence is not the new story.

Cross-workspace links use native document navigation, consistent with the
existing workspaces. This avoids mixed client/document history leaving the
Planning UI at the landing URL when Back is pressed before hydration. Scene
reading position also survives a reload from the longer reduced-motion page
into the default enhanced layout. Both paths have dedicated browser checks.

## Source Map

- `apps/web/src/components/landing/landing-page.tsx`: semantic story, real product previews, historical evidence.
- `apps/web/src/components/landing/illustrative-finding.tsx`: same-graph plan diagram, computed baseline/scenario comparison, explainable finding.
- `apps/web/src/components/landing/narrative-experience.client.tsx`: measured native scroll, four-chapter clock, fallbacks, reading continuity.
- `apps/web/src/components/landing/desktop-narrative-canvas.client.tsx`: lazy renderer, projected labels, visibility and error handling.
- `apps/web/src/components/landing/scene/drone-scene.ts`: persistent authored world and registered state changes.
- `apps/web/src/lib/landing/illustrative-scenario.ts`: stable synthetic graph, explicit disruption assumption, pure reachability evaluation.
- `apps/web/src/lib/landing/sample-desktop-story.ts`: deterministic, independently tested scene sampling.
- `apps/web/public/landing/product/capture-manifest.json`: actual UI capture provenance, qualifications, and hashes.
- `apps/web/scripts/landing-v4-smoke.mjs`: reproducible browser matrix, pixel and source assertions, reports and recordings.

## Local Use

From this landing worktree in PowerShell:

```powershell
Set-Location 'C:\Users\iputu\.codex\worktrees\fg-landing'
pnpm.cmd --filter @floodguard/web dev --hostname 127.0.0.1 --port 4310
```

Open `http://127.0.0.1:4310/`. Use a different free port if another server is
already listening. Do not build deployment profiles while this development
server is running; Next's build and dev processes share generated directories.

```powershell
pnpm.cmd --filter @floodguard/web test
pnpm.cmd --filter @floodguard/web lint
pnpm.cmd --filter @floodguard/web typecheck
pnpm.cmd --filter @floodguard/web verify:profiles
pnpm.cmd --filter @floodguard/web test:offline
pnpm.cmd --filter @floodguard/web test:csp
```

For browser checks against the exported competition build, from `apps/web`:

```powershell
$env:FLOODGUARD_V4_OUT = (Resolve-Path out).Path
$env:FLOODGUARD_V4_EVIDENCE = 'test-results/landing-v4/browser-rerun'
node scripts/landing-v4-smoke.mjs
```

The browser harness hosts that export on an ephemeral local port with the
repository's security headers, then closes its browser and server. It does
not deploy or submit reports. Use a new evidence directory for each run.

## Acceptance Boundary

This is a locally verified implementation candidate. Human comprehension
interviews, owner art approval, real Mae Sai road/facility validation, and
agency operational acceptance are separate and not fabricated as completed
stages. The existing separate GeoAI/main Planning result discrepancy is
documented in the claims audit; it was not silently altered by a landing task.

## Preview Packaging (2026-09-14)

The owner subsequently requested the `landing-page` branch and a Vercel Preview.
The existing root `vercel.json` builds the competition profile with
`pnpm build:web` and publishes `apps/web/out`; this does not require changing
the production branch or promoting a deployment. Hosted verification remains
separate from the local acceptance record above.

Sharing metadata now uses the authored V4 `desktop-v4/far.webp`. The two old
unverified aerial references, `hero-desktop.webp` and `hero-mobile.webp`, are
excluded from the commit and removed from generated exports by the postbuild
step. Original local reference files remain untouched. The profile artifact
check rejects either reference in a competition export. Raw browser receipts,
logs, and videos remain local under ignored `test-results`; the committed
documentation does not imply those files are included in Git.
