# Policy page: source and refresh record

The landing-linked `/policy/` page explains project policy for mentoring. Its fixed example lives in `apps/web/src/lib/policy-evidence.ts`; it does not change the Public, Planning or Studio calculations.

The example is a **historical worked example that predates the signed scoring frame**. The page titles it "Worked example from the 28 Sep study (before the signed scoring frame)" and shows its eight scores only inside one card that first states the caveats below. Nothing on the page computes an FPPS or a class.

## Why this source

The snapshot was reproduced once, on 29 September 2026, from commit `2e5a099ee075532e27236067810699ce6996c5c4`, the committed FPPS/playbook study. Source methods are [replay-fpps.ts](https://github.com/TUPRAM/flood-guard/blob/2e5a099ee075532e27236067810699ce6996c5c4/apps/web/src/lib/replay-fpps.ts), [fpps.ts](https://github.com/TUPRAM/flood-guard/blob/2e5a099ee075532e27236067810699ce6996c5c4/apps/web/src/lib/fpps.ts), and the [r2 manifest](https://github.com/TUPRAM/flood-guard/blob/2e5a099ee075532e27236067810699ce6996c5c4/apps/web/public/studies/mae-sai-2024-timeline/r2/timeline.json).

- Scenario: **12 September 2024, 12:00 ICT**, assumed stage **3.5 m**, shelter set **`reported_2024`**, WorldPop 2020 modelled residents, anchors **`replay_fpps_anchor_v1`**.
- Manifest SHA256: `5e2cea385ac7fe53952976e4d6cc75aed54b997b62d55aa7652fdcf83964eb6b`.
- Confidence is low. Every assigned class is E; accepted FPPS/action class remain unavailable. The score is a scenario index, not a flood probability or an official dispatch order.
- The source manifest has no generation timestamp. `generatedAt=null` preserves that absence; the commit time is recorded separately.

The supplied visualization commit `129ff03b6fe5e4467faac165d365f8fefc5e03e0` contains later r3 data, but its commit message identifies a WIP checkpoint with three failing page tests. It branches from the FPPS commit's parent and does not contain that FPPS feature. Consequently, r3 assets cannot substantiate the r2 scores. The separate integrated checkout had ongoing changes at inspection time, with no completed replacement FPPS artifact identified. The September 27 public-data analysis is a different population/access study; it is not a replacement scenario FPPS calculation. PR #35 first called this the “latest reproduced” study, meaning the source selection at review time. Since the signed decisions of 30 September 2026 the page calls it a historical worked example instead (next section).

## Status against signed decisions

The decisions are recorded in `docs/decision-log-d1-d16.md` (signed 30 September 2026, with owner decisions R1–R4). `POLICY_EVIDENCE` carries this status as data: `status: "historical_worked_example"`, `scoreLabel` (the chip text), `conformsToSignedFrame: false`, `computedBeforeProtocolV1b: true`, `reconstructionCoverageShare: 0.963`, `supersededLabels` (the r2 UNOSAT role that R1 overturned), `supersededBy: "planning assessment after v1b (D4, D6, D7)"`, `decisionRefs: ["D4", "D6", "D7", "R1", "R2"]`. `acceptedFpps` and `acceptedActionClass` stay `null` and `officialWarning` stays `false`.

| Decision | What it requires | Where the worked example stands |
|---|---|---|
| D4 (frozen score frame, plan v2 §3.4) | Flood = 100 × min(1, flooded share of the unit's non-permanent-water land ÷ 0.20); permanent water = WorldCover class 80 for every case, with JRC reported as a sensitivity note; 0.10 and 0.30 run one at a time, with the disclosure that 0.20 was chosen after seeing the data. Exposure = 100 × residents whose cell centre is inside the extent ÷ unit residents (WorldPop 2020; share only), with a 2024/2020 1 km population-vintage axis. Access gap = baseline-access-weighted mean of newly-lost shares; **public level:** hospital (vehicle, 30 min) + main-road entry (vehicle, 15 min); **pitch level:** adds DDPM located shelter (walking, 30 min); counted only for people with baseline access; facility axis public / corroborated / all listed. Road criticality = 100 × residents with a baseline route to any hospital or main road who lose all routes ÷ those residents. Vulnerability = 100 × clip((dependent share 0–14 + 60+ − P10) ÷ (P90 − P10), 0, 1), P10/P90 = national tambon percentiles of the WorldPop 2024 1 km dependent share, computed once in v1b before any case scoring; axes P5/P95 anchors and the terrain/remoteness proxy on O1 only. | **Does not conform.** It used `replay_fpps_anchor_v1`: flood saturates at 0.25 of the modelled area outside the mapped channel (no WorldCover mask); exposure is half the resident share (full at 0.25) and half a headcount (full at 5,000 people); access gap is the share of residents with flooded homes who have no dry shelter of the reported 2024 set within a 2 km walk, including people already out of reach before the flood; road criticality is class-weighted impassable road length (full at 0.5), not people cut off; vulnerability is the terrain/remoteness proxy share (full at 0.25). The page shows these differences in its "The signed scoring frame (D4)" table. |
| Reconstruction | The current replay (r3) models 100% of the district (`model_coverage` 305.6 of 305.6 km²). | Computed on **r2**, whose `model_coverage` at commit `2e5a099e` is 294.4 of 305.6 km², **96.3%** of the district. Its Copernicus DEM tile stopped at 100°E, so parts of Ko Chang (37.67 of 47.41 km²) and Si Mueang Chum (40.45 of 41.89 km²) were not modelled. Read from `git show 2e5a099ee075532e27236067810699ce6996c5c4:apps/web/public/studies/mae-sai-2024-timeline/r2/timeline.json` (`model_coverage`, `tambon_coverage`). |
| Blinding rule (plan v2 §2.3-5) | No FPPS, class or ensemble may be computed until protocol v1b is hashed (due Friday 2 October 2026). | Computed on 28–29 September 2026, **before v1b**. It is not a protocol result and must not be cited as the Mae Sai case score. |
| D6 | The v1 class rules (`src/floodguard/scoring.py`, `assign_action_class`) stay binding; v2 triggers appear only as a labelled secondary axis. | Its classes follow v1: low confidence forces E for all eight subdistricts. The page states the v1 thresholds exactly and prints "Class E never means safe." wherever E appears. |
| D7 | The Mae Sai replay is a narrative surface for O1 and SE1, not a new scored case. | The replay (`/studio/cases/mae-sai-2024/`) computes no FPPS and assigns no class, so the example is never refreshed from it. The page links the replay with its tier and calibration roles, in the replay's own words: GISTDA's 10 Sep flooded-area figure (about 9.9 km², "Mae Sai 6,182 rai") sets the 10 Sep 18:15 stage knot, so it is a calibration anchor (no GISTDA map is used), and the UNOSAT 3991 size check is calibration-informed, not independent (R1). `POLICY_EVIDENCE.currentReplay` holds both roles and the 9.9 km² figure, and a unit test reads them back from r3 `timeline.json`. The replay footer links back to `/policy/`. |
| R1 | UNOSAT 3991 is calibration-informed, not independent. | The pinned r2 manifest at `2e5a099e` still gives `unosat-3991` the role `independent_magnitude_check`. The page prints a note beside its "Pinned source" link that this label is superseded by R1 (30 Sep 2026), and `POLICY_EVIDENCE.supersededLabels` records the old and current values. |
| R2 | PR #35 is brought in and improved; any priority score shown carries its tier, method source and anchors. | Each headline tile carries a "Historical example · pre-D4 anchors · r2 · pre-v1b, not a protocol result" chip, and the same chip, with "Class E never means safe.", sits directly above the eight-row list. The card shows the tier (T1 scenario, model), the method source (`replay-fpps.ts` at `2e5a099e`) and the anchors (`replay_fpps_anchor_v1`, pre-D4) beside the numbers. |

Both cross-links exist only in the competition build. `scripts/build-profile.mjs` moves `/policy/`, `/studio/` and `/command/` aside for the public-production profile and `profile-artifact-smoke.mjs` fails that build if a link to them remains; `competitionPagesAvailable()` (`apps/web/src/lib/policy-links.ts`) leaves both links out of any other profile. In the competition build `write-offline-assets.mjs` caches `/policy/` and the replay route as core offline assets, so both links resolve offline; the replay's study data is saved for offline use after an online visit, and its footer (with the policy link) also shows while that data is unavailable.

## Record of the 29 September reproduction (do not run again)

**This is a record, not a procedure to repeat. Do not run it, before or after protocol v1b is hashed.** The script recomputes all eight pre-D4 FPPS rows and classes. It ran once, on 29 September 2026, before v1b; the page discloses that ("Computed on 28–29 September 2026, before protocol v1b was hashed"), and this section is where that run is reported, as plan v2 §2.3-5 requires for every run. A second run would be new FPPS and class computation for this page, which the refresh rule below forbids. After v1b the example is replaced by the planning assessment's recorded results, not re-audited.

The recorded check ran an in-memory TypeScript compilation of exact `git show` blobs. It read the original manifest, roads and access-node bytes from commit `2e5a099ee075532e27236067810699ce6996c5c4`, ran the source's `replayFpps` function, and compared all eight rows with the policy snapshot. It did not import the modified integrated checkout or save an intermediate source copy. The script is kept verbatim so a reviewer can read exactly what was computed; it ran from `apps/web` in PowerShell with the normal workspace dependencies (TypeScript is an existing web development dependency).

```powershell
@'
const cp = require('node:child_process');
const fs = require('node:fs');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const ts = require('typescript');
function compile(code, requireModule) {
  const exports = {};
  const result = ts.transpileModule(code, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
    reportDiagnostics: true,
  });
  assert.equal((result.diagnostics ?? []).length, 0);
  new Function('require', 'exports', 'module', result.outputText)(requireModule, exports, { exports });
  return exports;
}
const evidence = compile(fs.readFileSync('src/lib/policy-evidence.ts', 'utf8'), require).POLICY_EVIDENCE;
const read = p => cp.execFileSync('git', ['show', `${evidence.sourceCommit}:${p}`], { maxBuffer: 100 * 1024 * 1024 });
const cache = new Map();
function sourceModule(name) {
  if (cache.has(name)) return cache.get(name);
  const exports = compile(read(`apps/web/src/lib/${name}.ts`).toString(),
    name => name.startsWith('./') ? sourceModule(name.slice(2)) : require(name));
  cache.set(name, exports);
  return exports;
}
const timeline = sourceModule('flood-timeline');
const access = sourceModule('flood-timeline-evacuation');
const priority = sourceModule('replay-fpps');
const manifestBytes = read(evidence.sourceArtifact);
assert.equal(crypto.createHash('sha256').update(manifestBytes).digest('hex'), evidence.sourceSha256);
const manifest = JSON.parse(manifestBytes);
assert.equal(manifest.revision, evidence.revision);
assert.equal(manifest.confidence, evidence.confidence);
assert.equal(priority.REPLAY_FPPS_ANCHORS.version, evidence.scenario.anchorVersion);
const roads = JSON.parse(read('apps/web/public' + manifest.vectors.roads.href)).features.map(f => f.properties);
const a = manifest.access;
const nodes = access.parseAccessNodes(new Uint8Array(read('apps/web/public' + a.nodes.href)), a);
const stage = evidence.scenario.assumedStageMetres;
const replayStart = Date.parse(evidence.eventStart + 'T00:00:00+07:00');
const day = (Date.parse(evidence.scenario.timestamp) - replayStart) / 86400000;
assert.equal(timeline.stageAt(day, manifest.stage_anchors), stage);
const setIndex = a.sets.indexOf(evidence.scenario.shelterSet);
assert.ok(setIndex >= 0);
const stats = timeline.districtStats(manifest, stage, roads, []);
const rows = priority.replayFpps({
  tambonIds: Object.keys(manifest.tambon_coverage), accessTambons: a.tambons,
  modelledKm2: Object.fromEntries(Object.entries(manifest.tambon_coverage).map(([id, v]) => [id, v.modelled_km2])),
  floodedKm2: stats.tambon_flooded_km2, residents: manifest.population.tambon_totals,
  peopleInWater: stats.tambon_people_in_water ?? {},
  need: priority.evacuationNeed(nodes, setIndex, stage, a.levels, manifest.hand.step_m, a.tambons.length),
  nodeResidents: access.tambonResidents(nodes, a.tambons.length),
  vulnerable: priority.tambonVulnerable(nodes, a.tambons.length),
  roadWeightedKm: priority.tambonRoadWeights(roads),
  roadWeightedImpassableKm: priority.tambonImpassableRoads(roads, stage, manifest.impassable_depth_m),
  confidence: manifest.confidence,
});
assert.deepEqual(evidence.rankings.map(r => [r.id, r.score, r.actionClass]),
  rows.map(r => [r.id, r.fpps_0_100, r.action_class]));
evidence.stats.forEach((stat, index) => assert.equal(Number(stat.value), rows[index].fpps_0_100));
console.table(rows.map(r => ({ id: r.id, score: r.fpps_0_100, class: r.action_class })));
console.log('PASS: source hash, scenario selectors and all policy scores/classes match.');
'@ | pnpm exec node
```

Recorded result, 29 September 2026, in descending order: Mae Sai **89.34**, Si Mueang Chum **85.98**, Ban Dai **81.14**, Ko Chang **76.38**, Pong Pha **66.13**, Pong Ngam **53.93**, Huai Khrai **34.09**, Wiang Phang Kham **31.27**. All classes were **E**. It confirmed numerical reproduction only; it does not establish independent flood accuracy, practitioner approval, or operational acceptance.

## Refresh rule

Never compute FPPS or classes for this page, and do not rerun the 29 September reproduction above: it is kept only as the record of that one run. The page only shows recorded numbers.

**The snapshot is replaced only by D4/v1 planning-assessment results, and only after protocol v1b is hashed.** Until then, keep the worked example exactly as recorded, with its title, chips, caveat and status flags. When the planning assessment publishes Mae Sai results under the signed frame, replace the example with those results, set `conformsToSignedFrame` from what the assessment records, set `computedBeforeProtocolV1b: false`, record the assessment's source commit, input hashes, tier, confidence and anchor version, and remove the pre-D4 caveat only for rows that no longer need it. The r3 replay is never a source for scores (D7).

For that replacement, the earlier record-keeping rule still applies: use only a completed result with identifiable source code, immutable input artifacts and a reproducible outcome. Update the source commit, manifest digest, scenario selectors, population definition, normalization version, all rows and explanatory assumptions together. Take the numbers from the assessment’s own recorded outputs, not from a calculation run for this page; never substitute the active replay’s assets into an older calculation. Preserve absent timestamps and accepted-result nulls. Review component semantics and action wording when the source method changes; confirming water alone does not qualify all FPPS inputs. Then run the page's applicable checks and record their actual scope separately from scientific or operational acceptance.
