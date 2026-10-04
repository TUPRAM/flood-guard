# Unified lineage merge report

Date: 4 October 2026. Branch: `claude/unify-lineages`. Local only; nothing was pushed.

This branch puts the three lines of the FloodGuard repository on one branch, ready to merge into `master`.
The merge computed nothing: no FPPS, no action class, no ensemble.

## 1. What was merged

| Step | Commit | What it is |
|---|---|---|
| Start | `eebd353` | `claude/mae-sai-next`: `master` (`1f3107e`) plus the last Mae Sai replay wave (PR #42) |
| Merge 1 | `e04df38` | `codex/thai-event-selection` at `c3df131`, 82 commits: the scoring line (signed protocols v1a and v1b, E4, planning outputs, PR #31) |
| Merge 2 | `30fa9df` | `codex/geoid-radar-benchmark` at `cef5af8`, 10 more commits: the GEOID radar benchmark and the frozen M1-v2 (PR #41 on PR #32) |
| Fix | `04ffe6d` | Three shared-page resolutions finished |
| Fix | `32c1376` | The candidate-package report gets its own address |
| Fix | `7080f67` | The merged smoke scripts check the pages that are served |
| Fix | `f544a14` | Equity metric version 1 kept as the replay's reference |
| Fix | `59152d1` | One CI action version aligned |

Both merges are real merge commits (`git merge --no-ff`). Nothing was squashed, rebased or cherry-picked.
The fixes are ordinary commits on top; no merge commit was amended.

Checked after the merges:

- The signing commits `04bca20` (v1a) and `039b399` (v1b) are ancestors of the branch head.
- `planning_protocol_v1a.json` still hashes to `b6dc549c…a954` and `planning_protocol_v1b.json` to `6ed7d7e9…93e7`.
- All 70 files of the scoring line under `docs/proposal_execution/`, `outputs/planning_v1/` and
  `resources/planning_frames/` are byte-identical to that line. `RECEIPTS.jsonl` has its 51 lines, whole and in order.
- All 26 files the GEOID branch adds are byte-identical to that branch. The freeze receipt's hashes still match the
  frozen config, the tuning log and the two code modules (`geoid_m1_benchmark.py`, `sar_change_v2.py`).
- No lockfile was regenerated. The replay line never changed a dependency, so `pnpm-lock.yaml` and the three
  `uv.lock` files are the scoring line's. `pnpm install --frozen-lockfile` and `uv lock --check` both pass.

## 2. Resolution policy

- Mae Sai replay, policy page, study library, root landing, and their scripts, tests and data: the replay line wins.
- `docs/proposal_execution/`, `outputs/planning_v1/`, `resources/planning_frames/` and the scoring modules: the scoring line wins.
- Shared files (package scripts, CI, CSP, offline lists, smokes, shared components): both intents combined.
- Two modules of one purpose: both kept, listed in section 5.

The dry run on `claude/integration-dryrun` (`a80700d`) was reused for the 22 files neither line had changed since.
The replay line's later changes were carried into the other six. The dry run had not run the browser smokes;
running them is what found the fixes in section 4.

## 3. Conflicted files

Merge 1 had 28 conflicted files. Merge 2 had one.

| File | Resolution | Why |
|---|---|---|
| `.gitattributes` | Both rules kept | Each line pins its own byte-exact folder (`studies/`, `evidence-library/`) |
| `.github/workflows/ci.yml` | Replay's action versions plus scoring's full-history checkout | The protocol tests need the signing commits in the clone |
| `apps/web/next.config.ts` | Replay | The root page is the replay line's landing |
| `apps/web/tsconfig.json` | Replay | Same root entry |
| `apps/web/src/app/page.tsx` | Replay | The landing's own title and description |
| `apps/web/src/app/page.test.tsx` | Replay | It tests that landing |
| `apps/web/src/app/studio/page.tsx` | Replay | `/studio/` is the study library (see section 4) |
| `apps/web/package.json` | Both script sets | Replay's offline, studies and policy checks; scoring's evidence checks. Dependencies are scoring's |
| `package.json` | One `verify:frontend` with every step of both lines | Nothing either line ran is dropped |
| `vercel.json` | CSP of both | Replay fetches map tiles (connect-src); scoring adds the routing host |
| `apps/web/scripts/build-profile.mjs` | Both lists | The public build hides `command`, `studio`, `policy` and `public-cases` |
| `apps/web/scripts/write-offline-assets.mjs` | Both | Replay's export pack; scoring's evidence, brief and public-case assets |
| `apps/web/scripts/offline-smoke.mjs` | Both route lists; replay's landing and library text | Every route of both lines is checked |
| `apps/web/scripts/profile-artifact-smoke.mjs` | Both | Same, for the built artifact |
| `apps/web/scripts/browser-offline-smoke.mjs` | Both route lists; replay's landing | Same, in a browser |
| `apps/web/scripts/browser-public-profile-smoke.mjs` | Both | Replay's offline tile handling; every staff route of both lines must be absent |
| `apps/web/scripts/browser-profile-transition-smoke.mjs` | Replay's landing flow; both forbidden lists | The status pill hides on the landing, so it is read on `/public/` |
| `apps/web/scripts/csp-smoke.mjs` | Replay's map and location checks; both route lists | The map checks run on `/command/archive/`, where the map now is |
| `apps/web/src/components/command-workspace.tsx` | Replay's shared header, scoring's archive framing, and (fix) replay's research layer | See section 4 |
| `apps/web/src/components/command-workspace.test.tsx` | Replay's header checks; scoring's shorter banned-word list | "Candidate" and "non-operational" are now page text |
| `apps/web/src/components/studio-workspace.tsx` | Replay's shared header plus scoring's archive banner | One component serves both lines' pages |
| `apps/web/src/components/geo-map.tsx` | Replay | Its map background health is the fuller one. Scoring's block-image detection is not carried |
| `apps/web/src/components/geoai-real-panel.tsx` | Replay | The research panel policy |
| `apps/web/src/components/geoai-real-panel.test.tsx` | Replay | It tests that panel |
| `apps/web/src/components/public-home-page.tsx` | Both | Replay's priority labels and dated confidence line; scoring's navigation props and "candidate" status line |
| `apps/web/src/components/public-experience.test.tsx` | Both expectations | It tests the joined home page |
| `apps/web/src/components/pwa-register.tsx` | Both | Replay's self-hiding status pill; scoring's inline slot, wording and offline path list |
| `apps/web/src/components/root-public.tsx` | Scoring | The public page carries the `main-content` anchor itself |
| `.env.example` (merge 2) | One entry | Three lines described the same variable, `FLOODGUARD_EXTERNAL_DATA` |

## 4. Fixes after the merges

These are places where the two lines met without a textual conflict.

1. **Two pages at `/studio/`.** The replay line put its study library there; the scoring line put its
   candidate-package report there. The library keeps `/studio/`. The report is now at `/studio/candidate-report/`,
   unchanged, and the scoring line's links to the report and its "Studio" tab point to it.
2. **Two pages at `/command/`.** The scoring line's candidate overview is at `/command/`. The map workspace both
   lines share is at `/command/archive/`, with the scoring line's archive framing. The replay line's research layer
   had been dropped from it by the first merge; it is back, above the archive footer.
3. **Equity.** The scoring line moved `floodguard.equity` to metric version 2.0. The replay's own rule was written
   against the earlier version and its tests compared it with the module as it is now; 23 tests failed. `equity.py` stays at
   2.0. The earlier code is kept unchanged as `equity_v1.py`, used only as the replay's reference. No replay data,
   fixture or page text changed.
4. **Smoke scripts.** Git joined both lines' smoke scripts line by line, so some checks tested one line's page
   against the other line's expectation (landing text, map background states, the `/landing/` cache rule, the page
   language). Each check keeps its purpose and now reads the page that is served.
5. **Two small ones.** A test passes the props the joined home page needs; the planning-evidence page no longer
   has two `main-content` anchors.

## 5. Duplicates left for a later clean-up

Nothing was redesigned. These pairs do the same job in two places:

| Purpose | Replay line | Scoring line |
|---|---|---|
| Landing page | `components/landing-v1/` (served at `/`) | `components/landing/` and its assets in `public/landing/` (not served; its unit tests still run) |
| Equity gap | `replay_equity.py`, `equity_v1.py`, `flood-timeline-evacuation.ts` | `equity.py` (2.0) |
| Road closure rule | `flood_timeline.road_state`, `evacuation_access.closure_stage` (water depth) | `closure_rules.py` (share of the edge inside the extent) |
| Rights record | `rights_basis.py`, `rights_basis_4009_v1.json` | `automated_track/rights_basis_v1.json`, `SOURCES_AND_RIGHTS.md` |
| Wording guard | `wording_lint.py`, `replay-wording-rules.json`, `replay-wording-lint.ts` | `tests/test_automated_track_honesty.py`, the text audits in `evidence-library-assets.mjs` |
| Shelters | `shelter_validation.py`, `shelter_set_comparison.py` | `ddpm_shelters.py`, `shelter_corroboration.py` |
| Access | `evacuation_access.py` | `two_step_access.py`, `evidence_routes.py`, `evidence_connectivity.py` |
| Receipts and hashing | `bake_receipt.py`, `replay_manifest.py` | `file_snapshot.py`, `evidence_catalog.py`, `record_planning_protocol_receipt.py` |
| Evidence report page | `/studio/planning-evidence/` | `/studio/archive/` (same component, archive framing) |
| Historical archive | `/studio/archive/mae-sai-geoai/` | `/studio/archive/`, `/command/archive/` |
| Page header | `workspace-header.tsx` | the headers inside `candidate-case-context.tsx` and `evidence-library.tsx` |

Scripts that still point at pages the unified branch does not serve, and are not part of `verify:frontend`:
`qa:landing`, `qa:desktop`, `test:automated-gate-preview`, `art:desktop`, `art:landing` (the scoring line's landing),
and `qa:visual` and `workspace-browser-smoke.mjs` (they expect the map workspace at `/command/`). They were not run.

## 6. Where things are now

| What | Page | Code and data |
|---|---|---|
| Mae Sai replay | `/studio/cases/mae-sai-2024/` | `apps/web/src/components/mae-sai-*.tsx`, `apps/web/src/lib/flood-timeline*.ts`, `apps/web/public/studies/mae-sai-2024-timeline/r4/`, `scripts/build_mae_sai_flood_timeline.py`, `src/floodguard/flood_timeline.py` and `replay_*.py`, `docs/decision-log-d1-d16.md`, `docs/demo/` |
| Policy page | `/policy/` | `apps/web/src/components/policy-page.tsx`, `apps/web/src/lib/policy-*.ts` |
| Study library | `/studio/`, `/studio/studies/c2s-ms-20260915/`, `/studio/archive/mae-sai-geoai/` | `studio-library.tsx`, `c2s-study-*.tsx`, `apps/web/public/studies/` |
| Signed protocols | none | `docs/proposal_execution/planning_protocol_v1a.json`, `planning_protocol_v1b.json`, `RECEIPTS.jsonl`, `tests/test_planning_protocol.py` |
| Planning outputs | none | `outputs/planning_v1/`, `resources/planning_frames/`, `scripts/build_planning_context.py` (E4), `src/floodguard/planning_context.py`, `closure_rules.py`, `grade_join.py`, `normalisation.py`, `ddpm_shelters.py`, `planning_frames.py` |
| Public evidence (PR #31) | `/command/`, `/command/cases/`, `/public-cases/`, `/studio/candidate-report/`, `/studio/library/`, `/studio/brief/` | `apps/web/public/evidence-library/`, `briefs/`, `public-case-projections/`, `src/floodguard/evidence_*.py`, `scripts/build_evidence_library.py` |
| Radar benchmark | none | `docs/proposal_execution/automated_track/geoid_*`, `src/floodguard/geoid_m1_benchmark.py`, `geoid_m1_review.py`, `geoid_radar_benchmark.py`, `sar_change_v2.py`, `scripts/tune_geoid_m1_v2.py`, `score_geoid_m1_benchmark.py`, `outputs/geoid_*.json` |

## 7. Test results

Run on this branch on 4 October 2026.

| Check | Result |
|---|---|
| `pnpm install --frozen-lockfile` | Passed; lockfile unchanged |
| `pnpm verify:frontend` (lint, type check, contracts, web tests, evidence assets, both profiles, offline, CSP, studies, policy, evidence browser) | Passed end to end: 12 contract tests, 788 web tests in 88 files, 17 evidence asset tests, both profiles and the profile transition, 12 routes offline, all routes under the production headers, 57 study checks, 11 policy check groups, the evidence browser smoke |
| `python -m pytest -q`, local environment | 3193 passed, 5 skipped, 2 failed |
| `python -m pytest -q`, the CI job's locked dependency set | 3185 passed, 15 skipped, 0 failed (no external data set, as in CI) |
| Mae Sai bake `--verify` | Passed: 34 of 34 files identical (r4) |
| E4 builder `--verify` (case se1, vehicle) | Passed: join log, facility table, receipt and context all identical. No compute window was declared; a verify run writes nothing into Git |
| Planning protocol, E4, GEOID and bake tests on their own | 378 passed, 5 skipped |
| `scripts/verify_evidence_library.py` (the CI step) | Passed: 8 packages, 8 databases |
| `uv lock --check` for the root, the API and the runner | Passed |

The two local failures need the `requests` package, which the local environment lacks. It is a declared
dependency (the `evidence` extra); nothing was installed:

- `tests/test_evidence_acquisition.py::test_ngis_bounded_partial_response_is_not_complete`
- `tests/test_evidence_acquisition.py::test_ngis_error_body_does_not_become_geojson`

The five skips are by design: four protocol tests that apply only to a draft or read the receipt instead, and one
that needs `FLOODGUARD_MAE_SAI_PILOT_ROOT`.

CI: `.github/workflows/ci.yml` carries the jobs of both lines. The core job clones full history, installs
`uv sync --locked --all-extras`, runs the tests and verifies the public evidence packages. The frontend job runs
the joined `verify:frontend`. The core job's dependency set was installed from the local cache without a download.
One change to expect: the scoring line's `evidence` extra brings Pillow and `requests` into CI, so replay tests
that used to skip there for lack of Pillow now run.

## 8. For the owners to decide

1. **How to merge this branch.** Use "Create a merge commit". A squash or a rebase removes the signing commits
   from the history and `tests/test_planning_protocol.py` then fails on `master`. This branch already contains
   PR #42, so merging it also lands that work.
2. **What `/command/` is.** On `master` today it is the map workspace. On this branch it is the scoring line's
   candidate overview, and the map workspace is at `/command/archive/` under a "historical archive" banner. The
   landing and the policy page link to `/command/`.
3. **The candidate report's address** (`/studio/candidate-report/`), and whether the study library should list the
   scoring line's pages. Today the library does not link to them, and they do not link back to the library.
4. **Should the replay follow equity 2.0?** That changes the replay's rule, its TypeScript mirror, the parity
   fixture and page wording. Until then `equity_v1.py` stays.
5. **The scoring line's landing.** It is not served. Keep it, or remove it with its assets, its scripts and the
   seven packages only it uses (`gsap`, `@gsap/react`, `three`, `@react-three/fiber`, `lucide-react`,
   `@axe-core/playwright`, `@types/three`).
6. **Dependencies.** The site moves from Next 16.2.6 to 16.3.5 and the tests from Vitest 3.2.4 to 4.1.11, as on
   the scoring line. All checks pass on them.
7. **Referrer policy.** The header is the scoring line's `strict-origin-when-cross-origin`. The replay line had
   `no-referrer` and sets the policy on each map request itself, so the stricter header would also work.
8. **Site size.** `apps/web/public/evidence-library/` is 278 MB and `studies/` is 119 MB. Check the first preview
   deployment.
9. **The duplicates in section 5.**
10. **Install `requests` locally** (`uv sync --all-extras`) so the two tests above run outside CI too.
