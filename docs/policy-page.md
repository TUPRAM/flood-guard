# Policy page: source and refresh record

The landing-linked `/policy/` page explains project policy for mentoring. Its fixed example lives in `apps/web/src/lib/policy-evidence.ts`; it does not change the Public, Planning or Studio calculations.

## Why this source

The snapshot was reproduced on 29 September 2026 from commit `2e5a099ee075532e27236067810699ce6996c5c4`, the committed FPPS/playbook study. Source methods are [replay-fpps.ts](https://github.com/TUPRAM/flood-guard/blob/2e5a099ee075532e27236067810699ce6996c5c4/apps/web/src/lib/replay-fpps.ts), [fpps.ts](https://github.com/TUPRAM/flood-guard/blob/2e5a099ee075532e27236067810699ce6996c5c4/apps/web/src/lib/fpps.ts), and the [r2 manifest](https://github.com/TUPRAM/flood-guard/blob/2e5a099ee075532e27236067810699ce6996c5c4/apps/web/public/studies/mae-sai-2024-timeline/r2/timeline.json).

- Scenario: **12 September 2024, 12:00 ICT**, assumed stage **3.5 m**, shelter set **`reported_2024`**, WorldPop 2020 modelled residents, anchors **`replay_fpps_anchor_v1`**.
- Manifest SHA256: `5e2cea385ac7fe53952976e4d6cc75aed54b997b62d55aa7652fdcf83964eb6b`.
- Confidence is low. Every assigned class is E; accepted FPPS/action class remain unavailable. The score is a scenario index, not a flood probability or an official dispatch order.
- The source manifest has no generation timestamp. `generatedAt=null` preserves that absence; the commit time is recorded separately.

The supplied visualization commit `129ff03b6fe5e4467faac165d365f8fefc5e03e0` contains later r3 data, but its commit message identifies a WIP checkpoint with three failing page tests. It branches from the FPPS commit's parent and does not contain that FPPS feature. Consequently, r3 assets cannot substantiate the r2 scores. The separate integrated checkout had ongoing changes at inspection time, with no completed replacement FPPS artifact identified. The September 27 public-data analysis is a different population/access study; it is not a replacement scenario FPPS calculation. “Latest reproduced” describes this source selection at review time, not an automatic feed.

## Reproduce the fixed example

The original check ran an in-memory TypeScript compilation of exact `git show` blobs. It read the original manifest, roads and access-node bytes from the same commit, ran the source's `replayFpps` function, and compared all eight rows with the policy snapshot. It did not import the modified integrated checkout or save an intermediate source copy. The command below preserves that procedure without new dependencies or generated files.

Run from the repository's `apps/web` directory in PowerShell, after the normal workspace dependencies are installed. The source commit must be present in Git; check with `git cat-file -e '2e5a099ee075532e27236067810699ce6996c5c4^{commit}'`. If absent, obtain that source commit from the repository before continuing. TypeScript is an existing web development dependency.

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

Expected scores in descending order: Mae Sai **89.34**, Si Mueang Chum **85.98**, Ban Dai **81.14**, Ko Chang **76.38**, Pong Pha **66.13**, Pong Ngam **53.93**, Huai Khrai **34.09**, Wiang Phang Kham **31.27**. All classes are **E**. This confirms numerical reproduction only; it does not establish independent flood accuracy, practitioner approval, or operational acceptance.

## Refresh rule

Replace the snapshot only when a newer completed study has identifiable source code, immutable input artifacts and a reproducible result. Update the source commit, manifest digest, scenario selectors, population definition, normalization version, all rows and explanatory assumptions together. Re-run the source calculation against its own assets; never substitute the active replay's assets into an older calculation. Preserve absent timestamps and accepted-result nulls. Review component semantics and action wording when the source method changes; confirming water alone does not qualify all FPPS inputs. Then run the page's applicable checks and record their actual scope separately from scientific or operational acceptance.
