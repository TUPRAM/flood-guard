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
| Review fix | `b5af1cf` | The Public status pill stays in its slot on phones |
| Review fix | `f81af93` | The research table has its styles again, and every report it loads passes the scoring line's parser |
| Review fix | `a456ecf` | The shared header on the two archive pages marks the section and keeps the case query |
| Review fix | `9da8883` | The study library has its strict wording check again |
| Review fix | `95648a9` | The walkthrough's replay beat is no longer filed as archived; the replay's equity text names `equity_v1` |

Both merges are real merge commits (`git merge --no-ff`). Nothing was squashed, rebased or cherry-picked.
The fixes are ordinary commits on top; no merge commit was amended.

The "review fix" rows answer a review of this branch. Section 4, items 6 to 12, says what each one changed.
What the review found and left for the owners is in section 8, items 11 to 15. The owner answered on 4 October
2026 (decision log, R17): what Command is to become (item 2), the research table (item 11) and the offline install
list (item 12). Items 11 and 12 are built on this branch. Item 14 was not put to the owner; it was fixed alongside.
A second review, on 5 October 2026, checked that work and found six points; items 11, 12 and 14 say what it found
and what changed, and R17 now keeps what the owner decided apart from what was chosen while building.

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
| `apps/web/src/components/command-workspace.tsx` | Replay's shared header, scoring's archive framing, and (later commit) replay's research layer | See section 4, item 2, and owner decision 11 |
| `apps/web/src/components/command-workspace.test.tsx` | Replay's header checks; scoring's shorter banned-word list | "Candidate" and "non-operational" are now page text |
| `apps/web/src/components/studio-workspace.tsx` | Replay's shared header plus scoring's archive banner | One component serves both lines' pages |
| `apps/web/src/components/geo-map.tsx` | Replay | Its map background health is the fuller one. Scoring's block-image detection is not carried |
| `apps/web/src/components/geoai-real-panel.tsx` | Replay, and (review fix) the scoring line's parser | The research panel policy. The scoring line's own panel is not carried: its Command variant was a notice with links and no table, and its archive view was closed by default (owner decision 11) |
| `apps/web/src/components/geoai-real-panel.test.tsx` | Replay | It tests that panel. The scoring line's three tests of its own panel are not carried |
| `apps/web/src/components/public-home-page.tsx` | Both | Replay's priority labels and dated confidence line; scoring's navigation props and "candidate" status line |
| `apps/web/src/components/public-experience.test.tsx` | Both expectations | It tests the joined home page |
| `apps/web/src/components/pwa-register.tsx` | Both | Replay's self-hiding status pill; scoring's inline slot, wording and offline path list |
| `apps/web/src/components/root-public.tsx` | Scoring | The public page carries the `main-content` anchor itself |
| `.env.example` (merge 2) | One entry | Three lines described the same variable, `FLOODGUARD_EXTERNAL_DATA` |

Four files are not in this table because Git merged them without a conflict, and they were wrong afterwards:
`apps/web/src/app/public-theme.css`, `apps/web/src/components/geoai-real-panel.module.css`,
`docs/demo_walkthrough.md` and one branch of the wording check in `browser-offline-smoke.mjs`. See section 4,
items 6, 7, 10 and 11.

## 4. Fixes after the merges

These are places where the two lines met without a textual conflict.

1. **Two pages at `/studio/`.** The replay line put its study library there; the scoring line put its
   candidate-package report there. The library keeps `/studio/`. The report is now at `/studio/candidate-report/`,
   unchanged, and the scoring line's links to the report and its "Studio" tab point to it.
2. **Two pages at `/command/`.** The scoring line's candidate overview is at `/command/`. The map workspace both
   lines share is at `/command/archive/`, with the scoring line's archive framing. The scoring line had taken the
   GeoAI research panel out of this workspace on purpose: on that line the panel's Command variant was a notice
   with two links and no table, and its tests said so. Commit `04ffe6d` put the replay line's panel back above the
   archive footer, because the replay line's offline smoke and unit test read it. That reverses a decision of
   PR #31. It is not a repair; it is owner decision 11 in section 8.
   The two addresses were swapped on 5 October 2026 at the owner's request (section 8, item 2; decision log, R19):
   the map workspace is at `/command/` and the candidate overview at `/command/ver2/`.
3. **Equity.** The scoring line moved `floodguard.equity` to metric version 2.0. The replay's own rule was written
   against the earlier version and its tests compared it with the module as it is now; 23 tests failed. `equity.py` stays at
   2.0. The earlier code is kept unchanged as `equity_v1.py`, used only as the replay's reference. No replay data,
   fixture or page text changed.
4. **Smoke scripts.** Git joined both lines' smoke scripts line by line, so some checks tested one line's page
   against the other line's expectation (landing text, map background states, the `/landing/` cache rule, the page
   language). Each check keeps its purpose and now reads the page that is served.
5. **Two small ones.** A test passes the props the joined home page needs; the planning-evidence page no longer
   has two `main-content` anchors.

Found by the review of this branch and fixed:

6. **Status pill on phones (Public page).** The scoring line moved the pill into a slot under the header. The
   replay line had three phone rules that place the floating pill. Git kept both, and the replay rules were the
   more specific, so the pill sat 128 px below its slot, on top of "Make my plan". Measured at 390 by 844 before
   the fix: slot at y 57, pill at y 185. The three rules now apply only to a pill outside the slot. The offline
   browser smoke checks, at 320 and 390 px in both languages, that the pill is inside the slot and clear of the
   action buttons. It fails on the build from before the fix.
7. **Research table styles.** The merge kept the replay line's research panel and took the scoring line's
   stylesheet for it, which no longer had the seven classes the panel uses (`fpps`, `action`, `aA` to `aE`). On
   `/command/archive/` and `/studio/archive/mae-sai-geoai/` each class badge had `class="undefined undefined"`
   and no colour. The stylesheet is the replay line's again. A unit test now fails when the panel uses a class
   its stylesheet does not have.
8. **Research report check.** The scoring line showed the report only after `parseGeoaiResearchBundle` had found
   its four statements: not an official warning, candidate tier, report only, cannot feed the decision layer. The
   merge dropped that check. The panel now passes every report it loads through that parser, on both pages, and
   does not show a report that fails it. The parser also accepts preview images under the frozen study folder,
   because the historical study page reads the frozen copy of the report (still pinned by SHA-256).
9. **Header on the two archive pages.** The shared header named "Planning" as the current page on
   `/command/archive/` and "Studio" on `/studio/archive/`, although those links lead to other pages. It now marks
   them as the current section (`aria-current="true"`), and the three surface links carry the selected case query
   again, as the scoring line's own header did. The replay line's pages are unchanged.
10. **Wording check for the study library.** The joined smoke checked `/studio/` with the short list of banned
    words meant for the report pages below it. `/studio/` has the replay line's strict list again.
11. **Walkthrough.** Git joined both lines' edits at the top of `docs/demo_walkthrough.md`. The replay beat ended up
    under the heading "Archived synthetic-dashboard walkthrough" and a sentence that called everything below it
    archived. The pointer to the replay beat is now above that heading, the sentence names the archived sections,
    and the archive addresses are the ones served (`/studio/archive/`, `/studio/archive/mae-sai-geoai/`,
    `/command/archive/`).
12. **Equity wording.** The replay's rule, its tests and the parity fixture script named `floodguard.equity` as
    their reference in comments and error messages. They now name `floodguard.equity_v1`. Text only: the logic
    and the committed fixture are unchanged.

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
| GeoAI report loading | the loader and panel in `geoai-real-panel.tsx` | `lib/geoai-research-bundle.ts` (the parser; the replay panel uses it since the review fix). The scoring line's own panel body is not carried |
| Sentinel-1 change and water comparison | `sentinel1_vv`, `s1_anchor`, `s1_size_comparison` in `scripts/build_mae_sai_flood_timeline.py` | `sar_change_v2.py`, `scripts/build_mae_sai_flood_candidate.py`, `scripts/build_sentinel1_threshold_baseline.py` |
| Sentinel-2 water check | `optical_water_check.py` | `automated_optical_v2.py`, `automated_reference.py` |
| Export packs | `replay_exports.py` | `evidence_finals_export.py` |

Scripts that still point at pages the unified branch does not serve, and are not part of `verify:frontend`:
`qa:landing`, `qa:desktop`, `test:automated-gate-preview`, `art:desktop`, `art:landing` (the scoring line's landing),
and `qa:visual` and `workspace-browser-smoke.mjs` (they expect the map workspace at `/command/`). They were not run.
`test:live-api`, which `README.md` documents, is stale in the same way: `live-api-smoke.mjs` opens `/command/`
expecting the map workspace and `/studio/` expecting the evidence report. It needs both development servers and
was not run.
Since 5 October 2026 (R19) the map workspace is at `/command/` again, which is the address `qa:visual`,
`workspace-browser-smoke.mjs` and `live-api-smoke.mjs` open for it. What they expect of `/studio/` is unchanged.
They are still not part of `verify:frontend` and were not run after the swap.

Documents that name addresses the unified branch moved. They are the scoring line's documents and were not edited:

- `docs/proposal_execution/pitch_outline.md`, line 21: the demo path goes from `/command/` to `/studio/` keeping
  the case query. `/studio/` is now the study library, which ignores the query; the report is at
  `/studio/candidate-report/`. This folder stays byte-identical to the scoring line.
- `docs/evidence_library.md`, line 209: "the linked `/studio/` validation report" is now at
  `/studio/candidate-report/`.
- `docs/geoai_methodology.md`, lines 5 and 6, and `docs/positioning-and-claims.md`, lines 40 to 42 and 114 to 115,
  describe `/command/` as the map workspace and `/studio/` as the evidence workspace. They were already out of
  date on the scoring line, which had moved those to `/command/archive/` and `/studio/archive/` itself.
  Since 5 October 2026 (R19) what they say of `/command/` holds again: it is the map workspace.
- Since the same change, the `/command/` step of the demo path in `pitch_outline.md` opens the map workspace, which
  does not read the case query; the planning overview of the case is at `/command/ver2/`. In the same folder,
  `acceptance_checklist.csv` and `proposal_requirements.csv` name `apps/web/src/app/command/page.tsx` as the file of
  the overview, which is now `apps/web/src/app/command/ver2/page.tsx`. The folder was not edited.

## 6. Where things are now

| What | Page | Code and data |
|---|---|---|
| Mae Sai replay | `/studio/cases/mae-sai-2024/` | `apps/web/src/components/mae-sai-*.tsx`, `apps/web/src/lib/flood-timeline*.ts`, `apps/web/public/studies/mae-sai-2024-timeline/r4/`, `scripts/build_mae_sai_flood_timeline.py`, `src/floodguard/flood_timeline.py` and `replay_*.py`, `docs/decision-log-d1-d16.md`, `docs/demo/` |
| Policy page | `/policy/` | `apps/web/src/components/policy-page.tsx`, `apps/web/src/lib/policy-*.ts` |
| Study library | `/studio/`, `/studio/studies/c2s-ms-20260915/`, `/studio/archive/mae-sai-geoai/` | `studio-library.tsx`, `c2s-study-*.tsx`, `apps/web/public/studies/` |
| Signed protocols | none | `docs/proposal_execution/planning_protocol_v1a.json`, `planning_protocol_v1b.json`, `RECEIPTS.jsonl`, `tests/test_planning_protocol.py` |
| Planning outputs | none | `outputs/planning_v1/`, `resources/planning_frames/`, `scripts/build_planning_context.py` (E4), `src/floodguard/planning_context.py`, `closure_rules.py`, `grade_join.py`, `normalisation.py`, `ddpm_shelters.py`, `planning_frames.py` |
| Public evidence (PR #31) | `/command/ver2/` (at `/command/` until 5 October 2026), `/command/cases/`, `/public-cases/`, `/studio/candidate-report/`, `/studio/library/`, `/studio/brief/` | `apps/web/public/evidence-library/`, `briefs/`, `public-case-projections/`, `src/floodguard/evidence_*.py`, `scripts/build_evidence_library.py` |
| Radar benchmark | none | `docs/proposal_execution/automated_track/geoid_*`, `src/floodguard/geoid_m1_benchmark.py`, `geoid_m1_review.py`, `geoid_radar_benchmark.py`, `sar_change_v2.py`, `scripts/tune_geoid_m1_v2.py`, `score_geoid_m1_benchmark.py`, `outputs/geoid_*.json` |

## 7. Test results

Run on this branch on 4 October 2026. The first four rows were run again at `95648a9`, after the review fixes.
The other rows are from the run before the review and were not repeated. The review fixes changed no dependency,
lockfile, planning file or evidence-library file. The Python files they changed (comments and messages only) are
covered by the local run in the second row.

| Check | Result |
|---|---|
| `pnpm verify:frontend` (lint, type check, contracts, web tests, evidence assets, both profiles, offline, CSP, studies, policy, evidence browser) | Passed end to end: 12 contract tests, 795 web tests in 89 files, 17 evidence asset tests, both profiles and the profile transition, 12 routes offline (with the new status-pill check and the strict wording list on `/studio/`), all routes under the production headers, 57 study checks, 11 policy check groups, the evidence browser smoke |
| `python -m pytest -q`, local environment, external data set | 3193 passed, 5 skipped, 2 failed (the two below) |
| Mae Sai bake `--verify` | Passed: 34 of 34 files identical (r4) |
| Planning protocol, E4, GEOID and bake tests on their own (15 test files) | 334 passed, 4 skipped |
| `pnpm install --frozen-lockfile` | Passed; lockfile unchanged |
| `python -m pytest -q`, the CI job's locked dependency set | 3185 passed, 15 skipped, 0 failed (no external data set, as in CI) |
| E4 builder `--verify` (case se1, vehicle) | Passed: join log, facility table, receipt and context all identical. No compute window was declared; a verify run writes nothing into Git |
| `scripts/verify_evidence_library.py` (the CI step) | Passed: 8 packages, 8 databases |
| `uv lock --check` for the root, the API and the runner | Passed |

Checked again at `95648a9`: both signing commits are ancestors of the head, both protocol files have their
hashes, `RECEIPTS.jsonl` has its 51 lines, the 70 scoring-line files and the 26 GEOID files are byte-identical to
their lines, and the freeze receipt's hashes match.

Run again on 5 October 2026, on the fixes that answer the second review (section 8, items 11, 12 and 14). Those
fixes changed page code, the service worker, style sheets, the smoke scripts and three documents; no dependency,
lockfile, planning file, evidence-library file or Python file.

| Check | Result |
|---|---|
| `pnpm verify:frontend` | Passed end to end: 12 contract tests, 822 web tests in 91 files, 18 evidence asset tests, 21 service-worker and budget tests, both profiles (Public 55 files, 3.0 MB; competition 138 files, 10.5 MB, each under the 12 MB budget) and the profile transition, 12 routes offline, all routes under the production headers, 57 study checks, 11 policy check groups, the evidence browser smoke |
| Offline browser smoke, new checks | A study area saved by opening the Planning overview and opened again without a connection; a 31 MB area not saved by opening it and saved with its button; a save whose worker was stopped reported as interrupted (8 seconds) and finished on a second request; a removed area not saved again by opening it; the map notice at nine screen sizes in both languages; the notice on Command without a dead link offline |
| `python -m pytest -q` on `tests/test_planning_protocol.py` and the five test files that read the changed documents or the web sources | 218 passed, 4 skipped (the four protocol skips) |

The full Python suite was not run again: nothing it covers changed.

The two local failures need the `requests` package, which the local environment lacks. It is a declared
dependency (the `evidence` extra); nothing was installed:

- `tests/test_evidence_acquisition.py::test_ngis_bounded_partial_response_is_not_complete`
- `tests/test_evidence_acquisition.py::test_ngis_error_body_does_not_become_geojson`

The five skips are by design: four protocol tests that apply only to a draft or read the receipt instead, and one
that needs `FLOODGUARD_MAE_SAI_PILOT_ROOT`. The run of the 15 files on their own has the four protocol skips.

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
   **Decided on 4 October 2026 (decision log, R17):** Command is to be replaced entirely by a rescue-coordination
   exercise replay of Mae Sai 2024. A detailed plan is written first and the page is built in a later change.
   Nothing of it is built on this branch; until then `/command/` and `/command/archive/` stay as described here.
   **Changed on 5 October 2026 at the owner's request (R19).** The owner asked for the two addresses to be swapped,
   and the paragraph above describes the branch as it was before that. Now `/command/` is the map workspace, as on
   `master`, under the same "historical research" banner, and it is the default Planning page. The scoring line's
   candidate overview is at `/command/ver2/`, with the same content. `/command/archive/` holds one sentence with a
   link in each language and forwards to `/command/`, keeping the query of an old link, so that old links,
   bookmarks and saved offline copies keep working. `/command/cases/` is unchanged. Each of the two pages links to
   the other in both languages. The "Planning" link of every header, the landing and the policy page lead to
   `/command/`, the map workspace they were written for. From a page of a selected case that link opens the
   workspace, which does not read the case; the workspace carries the case on its link to the overview.
   The offline installation holds the three addresses (141 files, 10,512,158 bytes of the 12 MB budget), and the
   public-production build still ships none of them.
   **Still open.** The replacement of Command (R17, part 1), of which nothing is built on this branch. The address
   of the overview once the new page takes `/command/`: the plan of the new page proposes `/command/planning/` and
   keeps `/command/archive/` behind a menu link, which has to be reconciled with `/command/ver2/` and with the
   forward (R19, point h; question Q12 of `docs/owner_decision_sheet_2026-10-05.md`). The forward page, the link
   labels and the page title are choices made while building (R19, points a to d), for the owner to confirm or
   change.
3. **The candidate report's address** (`/studio/candidate-report/`), and whether the study library should list the
   scoring line's pages. Today the library does not link to them, and they do not link back to the library.
   The scoring line's header on `/studio/archive/` also had "Decision brief", "Evidence library" and "Archive"
   entries; the shared header has the three surfaces only, so that page has no header link to `/studio/brief/` or
   `/studio/library/`.
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

Found by the review and left for the owners:

11. **The research table on `/command/archive/`.** On the scoring line this page had no research table: a notice
    said the earlier scores "are not accepted event-response priorities" and linked to the current brief. After
    the merge the page showed the replay line's panel: eight subdistricts sorted by research FPPS, with their A to
    E research classes, under "Report only".
    **Decided on 4 October 2026 (R17) and done:** the GeoAI research report's table is off Command.
    `/command/archive/`, where the panel was, and `/command/` show a short notice: the earlier scores are not
    accepted event-response priorities, and the report's score table is kept only in Studio's archive, with a link.
    The report, with its table, is shown only in Studio's archive (`/studio/archive/mae-sai-geoai/`), labelled
    "Historical research · report only". The unit tests and the offline smoke check the notice on Command and the
    table in Studio.
    **Still on `/command/archive/`, and open for the owner:** the map workspace's own retained ranking. It shows a
    research FPPS and a class for each of the eight subdistricts: an "FPPS ranking" rail with a score and a class
    badge in every row, the selected area's FPPS readout, the A to E legend, and the map's text list ("Mae Sai:
    class E, FPPS 18.0, low" and seven more rows). These come from the planning bundle, not from the GeoAI
    report, and the page says above them that they "are retained research comparisons, not accepted
    event-response priorities". Their values differ from the report's: Ko Chang is class E with 53.6 on the
    workspace and class D with 44 in the report. The owner's answer was about the report's table; whether the
    retained ranking should also leave the page before Command is replaced (item 2) was not asked. It stays until
    the owner says. The first notice said "the per-subdistrict research score table is no longer shown on
    Planning", which was not true of this page. Since the review of 5 October the notice names the report's table
    only, and on `/command/archive/` it adds that the ranking, FPPS and classes still shown there are a separate
    retained comparison whose values differ from the report's. The offline check now fails when `/command/` shows
    any research score or class, and when `/command/archive/` shows a score that is not one of its eight retained
    values; before, its search for the report panel's headings could not see the retained ranking at all.
    Offline, the notice's link to the report led to the browser's error page, because the report's page is not in
    the install list (the page is 18.7 kB, its files 1.9 MB; with them the list would be about 12.4 MB, over the
    12 MB budget). Without a connection the notice now says that the report needs one, and the offline smoke
    checks that on both pages.
    **Since 5 October 2026 (R19).** The map workspace is the default Planning page at `/command/`. So what this
    item says of `/command/archive/` is now true of `/command/`, and what it says of `/command/` is true of
    `/command/ver2/`; `/command/archive/` only forwards. The retained ranking therefore stands on the default
    Planning page again: the "FPPS ranking" rail with a score and a class badge in every row, the selected area's
    readout, the A to E legend and the map's text list. It is labelled as before, above the ranking: its scores and
    classes "are retained research comparisons, not accepted event-response priorities". The notice below it is the
    one described above (the GeoAI report's table is kept in Studio's archive as historical research; the ranking,
    FPPS and classes shown on the page are a separate retained comparison whose values differ from the report's).
    `/command/ver2/` carries the notice without that addition and shows no research score or class.
    The owner's request was about the two addresses and did not mention the ranking, so the question above is
    **still open for the owner** (R17, point g; question Q5 of `docs/owner_decision_sheet_2026-10-05.md`): whether
    the retained ranking stays once the new exercise page takes `/command/`, and before any score of the protocol
    appears on Command.
    The checks moved with the pages. The static offline check fails when `/command/ver2/` or the forward at
    `/command/archive/` shows any research score or class, when `/command/` shows a score that is not one of its
    eight retained values, and when a score or a class stands on `/command/` before the label. The browser check
    measures at 1280 px and on a phone that the label is above the first score, follows the links between the two
    pages in both languages, opens the forward with and without a connection, and checks on both pages that the
    notice's link to the report is a sentence when there is no connection.
12. **What a browser must download before the site works offline.** After the merge the install list was 84
    files, 297.6 MB, plus 75 script chunks, 3.3 MB: 301 MB together. The evidence library was 290.6 MB of it
    (largest file 66.4 MB), the briefs 2.7 MB, everything else 4.3 MB. Installation is all or nothing, the
    "available offline" status and the replay's on-request data wait for it, and each new deployment downloads it
    again.
    **Decided on 4 October 2026 (R17):** the catalogue and the pages stay in the automatic list, and each study
    area's package is saved only when someone opens it, as the replay already does.
    **Built.** Measured on the competition build: the install list is now 61 files, 7.1 MB, plus 77 script and
    style chunks, 3.4 MB: 138 files, 10.5 MB (10,494,397 bytes; 10,480,958 before the review of 5 October, whose
    fixes added 13 kB of page code). It holds the application, the pages, the
    library's catalogue (44 kB), the public case indexes (35 kB), the eight briefs (2.7 MB) and the files it held
    before for the Public and Mae Sai views (4.0 MB). The replay's own budgets are unchanged (6.5 MB of data,
    1.0 MB of exports, both saved once the replay has rendered).
    Since the swap of 5 October 2026 (R19; item 2) the list also holds the page at `/command/ver2/` and its page
    code: 141 files, 10,512,158 bytes, still 10.5 MB of the 12 MB budget.
    A study area is its package file or files, its terrain preview and the report: 101.8 MB for all six (5.5 MB
    to 51.3 MB each). The first build saved an area only when the reader pressed "Save this area for offline
    use". The review of 5 October found that this was not the decision: `/command/` and five other pages, opened
    with a connection, were empty without one until the button had been pressed. Now a page that has shown an
    area's checked package asks the worker to keep the area, with no button pressed. Measured: the Planning
    overview opened once with a connection saved Mae Sai core (3 files, 9.3 MB), and every page of that case then
    opened without one. The worker stores a file only when its SHA-256 matches (the catalogue's hash for a
    package), keeps saved areas in a cache apart from the per-build cache so that a new deployment keeps every
    unchanged file, and removes an area on request. Offline, a page of an area that is not saved says so and
    requests nothing.
    While a save runs, the page asks the worker every 4 seconds whether it is still working on it. Before, a save
    whose worker the browser had stopped left the row on "Saving and checking each file…" with its button
    disabled until the page was reloaded. Now the row says that the save stopped and can be tried again
    (measured: 8 seconds after the worker was stopped), files that had passed their check are kept, and a save
    that stored nothing leaves no empty cache.
    **Choices made while building; the owners have not decided them** (R17, a to e): the hard budget of 12 MB,
    which fails the build, the artifact check and the offline check above it; an area larger than 20 MB is saved
    only with its button (Bang Ban and Sena, 31.0 MB, and Rangsit, 51.3 MB; the other four, 5.5 to 14.2 MB, are
    saved when opened); nothing is saved on open when the browser asks to use less data, and a copy the reader
    removed is not saved again until the reader asks; the eight database archives a package offers for download
    (188.8 MB, up to 66.4 MB each) are never part of a saved copy, and their links say that they need a
    connection. Say if any of these should be different.
13. **The "Studio" link in the eight case briefs.** Each brief in `apps/web/public/briefs/` links "Studio" to
    `/studio/?aoi=...`, which is now the study library and ignores the case. The link comes from
    `build-case-briefs.mjs`, line 294. Rebuilding the briefs changes the `html_sha256` and `pdf_sha256` that
    `briefs/catalog.json` pins for each of the eight, so it was not done. The target would be
    `/studio/candidate-report/`.
14. **The map notice on phones (Public page).** When the map background cannot load, the notice covered part of
    "View map results as a list": 73 by 39 px at 390 by 844, 88 by 46 px at 375 by 812, 122 by 46 px at 320 by
    844. The list button is on top, so it hid the first words of the notice; the button itself still worked,
    which is why the smoke passed. Cause: the notice is the replay line's (a sentence and three buttons, 159 px
    tall) and was placed 272 px above the map's lower edge, while the scoring line's intro block and status slot
    take about 200 px above the map that the replay line's page did not have.
    **Not put to the owner; fixed alongside item 12.** First fix (4 October): up to 680 px wide the notice became
    one line and one button ("Map background unavailable", "Options"), 62 px tall, still placed from the map's
    lower edge. The sentence and the actions open behind the button and fold back after an action.
    The review of 5 October measured that fix at more sizes. It was clear only on a screen about 800 px tall or
    more. On the same phones inside a browser tab (390 by 664, 375 by 635, 375 by 667, 393 by 659, 360 by 640,
    360 by 660, 320 by 568) the notice lay under the search field for its whole width and 38 px of its height:
    the sentence could not be read and "Options" could not be tapped. At 360, 375 and 390 by 740 the list button
    covered 44 to 74 px of it again. The first record gave the limit as "667 px tall or shorter" with 27 px and
    22 px of contact, which understated both. Laptop windows had the same fault with the long form of the notice
    (1024 by 768, 1280 by 720 and 1366 by 650: under the search field, or partly above the map).
    Second fix (5 October): the notice is no longer placed from the lower edge. On the Public page it stands in
    one column with the list button, directly below it, at every width, in its short form (62 px; the English line
    wraps to two lines inside that height at 320 px). While it is shown the map is at least 448 px tall, so that
    the row stays clear of the attribution, the priority card and the tools, which are placed from the lower
    edge; on a short screen the page scrolls 88 px further for that. The notice is not shown while the background
    is loading for the first time or after a pan, only once a problem is known, so an ordinary load moves
    nothing. Measured in Thai and English at 320 by 844, 375 by 812, 390 by 844, 390 by 664, 375 by 635, 360 by
    740, 320 by 568, 1280 by 720 and 1366 by 650, and with the location card shown at 390 by 664: no overlap with
    the search field, the list button, the attribution, the priority card or any map tool, and a tap on the text
    and on the button reaches the notice. The offline smoke checks all of these.
    Seen while measuring and not changed, because they do not involve the notice: with the map at its smallest
    (360 px tall) the attribution line overlaps the list button by 3 px and, at 320 px wide in English, the
    priority card by 10 px; the location card of the address search can lie over the map tools on a short map.
15. **The stale addresses in the scoring line's documents**, listed at the end of section 5.
