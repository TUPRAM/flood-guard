import { existsSync, readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { resolve } from "node:path";
import { auditEvidenceLibrary, EVIDENCE_AREA_CACHE, EVIDENCE_CATALOG_ASSET, readWorkerEvidenceAreas } from "./evidence-library-assets.mjs";
import { megabytes, verifyOfflineInstall } from "./offline-install-budget.mjs";
import { firstWorkspaceScoreAt, forbiddenValues, readReportScores, readRetainedRanking, readWorkspaceMarkup, researchScoreMarkup, researchScoreTraces, visibleText, workspaceRankingProblems } from "./research-score-guard.mjs";

import { readCaseReplay } from "./case-replay-inventory.mjs";

const out = resolve(process.cwd(), "out");
const routeFiles = ["index.html", "public/index.html", "public-cases/index.html", "command/index.html", "studio/archive/command-workspace/index.html", "command/planning/index.html", "command/cases/index.html", "command/archive/index.html", "command/ver2/index.html", "command/exercise/index.html", "studio/index.html", "studio/planning-evidence/index.html", "studio/candidate-report/index.html", "studio/library/index.html", "studio/brief/index.html", "studio/archive/index.html"];
const requiredPublicAssets = [
  "manifest.webmanifest",
  "sw.js",
  "floodguard-logo.png",
  "offline-demo/bundle.json",
  "offline-demo/areas.geojson",
  "offline-demo/roads.geojson",
  "offline-demo/context.geojson",
  "offline-demo/mae-sai/bundle.json",
  "offline-demo/mae-sai/manifest.json",
  "offline-demo/mae-sai/areas.json",
  "offline-demo/mae-sai/roads.json",
  "offline-demo/mae-sai/facilities.json",
  "offline-demo/mae-sai/access-hotspots.json",
  "proposal-evidence-status.json",
  "offline-assets.json",
  "evidence-library/catalog.json",
];

for (const relative of [...routeFiles, ...requiredPublicAssets]) {
  const path = resolve(out, relative);
  if (!existsSync(path)) throw new Error(`Offline artifact missing: ${relative}`);
}

const routeExpectations = {
  "index.html": [/data-fg-landing/i, /See the flood/i, /Understand what it changes/i, /illustrat/i, /href="\/public\/"/i, /href="\/command\/"/i, /href="\/studio\/"/i],
  "public/index.html": [
    /public-app-header/i,
    /FloodGuard/i,
    /public-tab-home/i,
    /public-tab-report/i,
    /public-tab-shelter/i,
    /public-tab-prepare/i,
    /public-tab-sos/i,
  ],
  "public-cases/index.html": [/Understand the study cases/i, /Candidate research evidence/i, /Non-operational/i],
  // The Planning addresses since the owner's decision of 7 Oct 2026 (decision log R24): the Command exercise replay
  // is the default page at /command/, the planning overview is at /command/planning/, the older map workspace is
  // historical research in Studio's archive, and /command/archive/, /command/ver2/ and /command/exercise/ forward.
  "command/index.html": [
    /<title>Command exercise replay: Mae Sai, September 2024/,
    /data-command-exercise="true"/,
    // The shared site header, with this page as the Planning page, and the exercise banner under it.
    /data-command-site-header="true"/,
    /<a href="\/command\/" aria-current="page">Planning<\/a>/,
    /Exercise replay/,
    /not an official warning/i,
    /not real-time/i,
  ],
  "studio/archive/command-workspace/index.html": [
    /<title>Historical Planning map workspace \(retained research comparison\) \| FloodGuard/,
    /class="command-page/,
    /Historical Mae Sai research archive/i,
    /not accepted event-response priorities/i,
    // The page is historical research in Studio's archive: its header marks the Studio section, and no Planning page.
    /<a href="\/studio\/" aria-current="true">Studio<\/a>/,
    /<a href="\/command\/">Planning<\/a>/,
    // The research score table is not on Command: a notice says where the historical report is kept.
    /data-research-report-notice="true"/,
    /Earlier research scores and classes are not accepted event-response priorities/,
    /href="\/studio\/archive\/mae-sai-geoai\/"/,
    // This page keeps its own ranking, scores and classes: it says what they are, and the notice says so too.
    /Subdistrict scores and classes below are retained research comparisons, not accepted event-response priorities/,
    /data-research-retained-ranking="true"/,
    /The ranking, FPPS and classes still shown on this page are a separate retained research comparison/,
    // A link to the other Planning page, the overview.
    /<a href="\/command\/planning\/" data-planning-overview-link="true">Current planning overview<\/a>/,
    /<a href="\/command\/planning\/">Open the current candidate overview<\/a>/,
  ],
  "command/planning/index.html": [
    /<title>Planning overview \| FloodGuard/,
    /data-planning-candidate=/,
    /Planning case/i,
    /Candidate.*low confidence/i,
    /Loading case catalog/i,
    // The header's Planning link leads to the exercise replay, another page: it marks the section only.
    /<a href="\/command\/" aria-current="true">Planning<\/a>/,
    // The research score table is not on Command: a notice says where the historical report is kept.
    /data-research-report-notice="true"/,
    /Earlier research scores and classes are not accepted event-response priorities/,
    /href="\/studio\/archive\/mae-sai-geoai\/"/,
    // A link to the default Planning page, there before any case has loaded.
    /<a href="\/command\/" data-planning-workspace-link="true">← To the Command exercise replay<\/a>/,
  ],
  "command/cases/index.html": [/Study-area decision brief/i, /Candidate research evidence/i, /Non-operational/i],
  "command/archive/index.html": [
    /<title>Moved to Studio(?:'|&#x27;)s archive · ย้ายไปที่คลังของ Studio แล้ว \| FloodGuard/,
    /data-command-forward="\/studio\/archive\/command-workspace\/"/,
    /<p lang="en">This page has moved\. The older Planning map workspace, kept as historical research, is now at <a href="\/studio\/archive\/command-workspace\/">\/studio\/archive\/command-workspace\/<\/a>\.<\/p>/,
    /<p lang="th">หน้านี้ย้ายแล้ว พื้นที่ทำงานแผนที่เดิมซึ่งเก็บไว้เป็นงานวิจัยย้อนหลังอยู่ที่ <a href="\/studio\/archive\/command-workspace\/">\/studio\/archive\/command-workspace\/<\/a><\/p>/,
  ],
  "command/ver2/index.html": [
    /<title>Moved to the planning overview · ย้ายไปที่ภาพรวมเพื่อการวางแผนแล้ว \| FloodGuard/,
    /data-command-forward="\/command\/planning\/"/,
    /<p lang="en">This page has moved\. The planning overview is now at <a href="\/command\/planning\/">\/command\/planning\/<\/a>\.<\/p>/,
    /<p lang="th">หน้านี้ย้ายแล้ว ภาพรวมเพื่อการวางแผนอยู่ที่ <a href="\/command\/planning\/">\/command\/planning\/<\/a><\/p>/,
  ],
  "command/exercise/index.html": [
    /<title>Moved to Planning · ย้ายไปที่หน้าการวางแผนแล้ว \| FloodGuard/,
    /data-command-forward="\/command\/"/,
    /<p lang="en">This page has moved\. The Command exercise replay is now at <a href="\/command\/">\/command\/<\/a>\.<\/p>/,
    /<p lang="th">หน้านี้ย้ายแล้ว หน้าฝึกซ้อมสั่งการอยู่ที่ <a href="\/command\/">\/command\/<\/a><\/p>/,
  ],
  "studio/index.html": [
    /Every result has a context/i,
    /Research studies/i,
    /Planning evidence/i,
    /Historical studies/i,
    /Local accuracy unmeasured/i,
  ],
  "studio/planning-evidence/index.html": [
    /Validation &amp; evidence report|Validation & evidence report/i,
    /Source time/i,
    /Confidence/i,
    /Technical verification/i,
    /Observed-data validation/i,
    /Operational authorization/i,
  ],
  "studio/candidate-report/index.html": [
    /Evidence status and decision boundary/i,
    /verified checksum does not qualify/i,
    /Loading case catalog/i,
  ],
  "studio/library/index.html": [/Study-area evidence library/i, /Non-operational/i, /Candidate research evidence/i],
  "studio/brief/index.html": [/Study-area decision brief/i, /Non-operational/i, /Candidate research evidence/i],
  "studio/archive/index.html": [/Historical Mae Sai technical report/i, /separate evidence context/i],
};

for (const relative of routeFiles) {
  const html = readFileSync(resolve(out, relative), "utf8");
  for (const expectedCopy of routeExpectations[relative]) {
    if (!expectedCopy.test(html)) {
      throw new Error(`${relative} lacks polished route copy matching ${expectedCopy}`);
    }
  }
  const resourceUrls = [...html.matchAll(/<(?:script|link)\b[^>]*(?:src|href)="([^"]+)"/gi)].map((match) => match[1]);
  const external = resourceUrls.filter((url) => /^https?:\/\//i.test(url));
  if (external.length) throw new Error(`${relative} has external runtime resources: ${external.join(", ")}`);
}

// The GeoAI research report, with its research FPPS and A-E classes, is served by Studio's archive only.
const builtPage = (relative) => readFileSync(resolve(out, relative), "utf8");
for (const relative of ["command/index.html", "studio/archive/command-workspace/index.html", "command/planning/index.html", "command/archive/index.html", "command/ver2/index.html", "command/exercise/index.html"]) {
  const retained = builtPage(relative).match(/GeoAI research report|geoai-real-title|Research FPPS|Research class|GEOAI RESEARCH/);
  if (retained) throw new Error(`${relative} still carries the research report panel: ${retained[0]}`);
}
// What "a research score or class" means here is the list of written forms in research-score-guard.mjs: the ranking's
// markup, the word FPPS followed by a number, a class followed by a letter A to E, and the retained and the report's
// values as numbers of their own. A score written in another way is not found; the browser check applies the same
// list to the overview once a case has loaded, in English and in Thai.
const retainedRanking = readRetainedRanking(out);
const reportScores = readReportScores(out);
const retainedScores = new Set(retainedRanking.map((row) => row.score));
if (retainedRanking.length !== 8 || retainedScores.size !== 8) throw new Error("The planning bundle does not hold eight retained subdistricts with eight different values.");
if (reportScores.some((value) => retainedScores.has(value.toFixed(1)))) {
  throw new Error("A retained planning-bundle score equals a score of the GeoAI report: the workspace check cannot tell them apart.");
}
const forbiddenScores = forbiddenValues(retainedRanking, reportScores);
// The Planning overview, at /command/planning/, and the three addresses that only forward show none of these forms.
// In the built file the overview is the page before a case has loaded. The exercise replay at /command/ is not in
// this list: it shows the class of the signed protocol for a scenario, read from a published result file, with the
// words that say so; it shows no research score, which the check of the GeoAI report's panel above covers.
const FORWARD_PAGES = ["command/archive/index.html", "command/ver2/index.html", "command/exercise/index.html"];
for (const relative of ["command/planning/index.html", ...FORWARD_PAGES]) {
  const html = builtPage(relative);
  const traces = [...researchScoreTraces(visibleText(html), forbiddenScores), ...researchScoreMarkup(html)];
  if (traces.length > 0) throw new Error(`${relative} shows a written form of a research score or class: ${traces.join(", ")}`);
}
// The overview's notice does not speak of a ranking on the page.
if (builtPage("command/planning/index.html").includes("data-research-retained-ranking")) {
  throw new Error("command/planning/index.html describes a retained ranking it does not show.");
}
// A forward has no notice and no page of its own.
for (const relative of FORWARD_PAGES) {
  const forwardHtml = builtPage(relative).replace(/<script\b[\s\S]*?<\/script>/g, " ");
  const forwardContent = forwardHtml.match(/data-research-report-notice|class="command-page|data-planning-candidate|<table\b|<h1\b|<h2\b/);
  if (forwardContent) throw new Error(`${relative} has content of its own beside the forward: ${forwardContent[0]}`);
}
// The one exception, stated on the page itself (see the expectations above): the map workspace keeps its own retained
// ranking. Since 7 Oct 2026 it is historical research at /studio/archive/command-workspace/ (R24; it was the default
// Planning page before). Its ranking rail and the map's text list hold the eight rows of the
// planning bundle, each with the bundle's value and class, and no number with one decimal on the page is anything
// but one of those eight values. So a value of the GeoAI report's table, or a ninth value, written with a decimal
// fails wherever it stands on the page.
const workspace = readWorkspaceMarkup(builtPage("studio/archive/command-workspace/index.html"));
const workspaceProblems = workspaceRankingProblems(workspace, retainedRanking);
if (workspaceProblems.length > 0) throw new Error(`studio/archive/command-workspace/index.html does not show its retained ranking as the planning bundle holds it: ${workspaceProblems.join("; ")}`);
// The page's label stands before the first score and the first class a reader meets, whatever their written form:
// in the banner above the workspace, and again at the head of the small-screen summary.
const workspaceHtml = builtPage("studio/archive/command-workspace/index.html").replace(/<script\b[\s\S]*?<\/script>/g, " ");
const workspaceLabel = "Subdistrict scores and classes below are retained research comparisons, not accepted event-response priorities.";
const labelAt = workspace.text.indexOf(workspaceLabel);
const firstNumberAt = firstWorkspaceScoreAt(workspace.text);
const firstMarkAt = workspaceHtml.search(/class="[^"]*\b(?:rank-score|fpps-block|decision-class|class-[a-e])\b/);
if (labelAt < 0 || firstNumberAt < 0 || labelAt > firstNumberAt || firstMarkAt < 0 || workspaceHtml.indexOf(workspaceLabel) > firstMarkAt) {
  throw new Error("studio/archive/command-workspace/index.html shows a retained score or class before the label that says what they are.");
}
const summaryLabelAt = workspace.text.indexOf("The FPPS and class below are retained research comparisons, not accepted event-response priorities.");
if (summaryLabelAt < 0 || summaryLabelAt > firstNumberAt) {
  throw new Error("studio/archive/command-workspace/index.html shows its small-screen readout before the label of that summary.");
}
const historicalStudyHtml = readFileSync(resolve(out, "studio", "archive", "mae-sai-geoai", "index.html"), "utf8");
for (const expected of [/HISTORICAL RESEARCH · REPORT ONLY/, /aria-labelledby="geoai-real-title"/, /GeoAI research report/, /Report only/]) {
  if (!expected.test(historicalStudyHtml)) throw new Error(`Studio's archive lacks the historical research report: ${expected}`);
}

const publicHtml = readFileSync(resolve(out, "public", "index.html"), "utf8");
for (const retiredTab of ["map", "shelters", "data"]) {
  if (publicHtml.includes(`id="public-tab-${retiredTab}"`)) {
    throw new Error(`Public artifact retains retired navigation: ${retiredTab}`);
  }
}
for (const removedChrome of ["public-boundary-banner", "public-brand-mark"]) {
  if (publicHtml.includes(removedChrome)) {
    throw new Error(`Public artifact retains removed chrome: ${removedChrome}`);
  }
}

const serviceWorker = readFileSync(resolve(out, "sw.js"), "utf8");
if (
  serviceWorker.includes("__BUILD__") ||
  serviceWorker.includes("__APP_PROFILE__") ||
  serviceWorker.includes("__CACHE_CREATED_AT__") ||
  serviceWorker.includes("__PROFILE_CORE_ASSETS__") ||
  serviceWorker.includes("__OPTIONAL_LANDING_ARTWORK__") ||
  serviceWorker.includes("__OPTIONAL_EVIDENCE_AREAS__") ||
  !/floodguard-offline-[0-9a-f]{12}/.test(serviceWorker)
) {
  throw new Error("Service worker does not use a content-derived cache version");
}
for (const route of ["/", "/public/", "/public-cases/", "/command/", "/studio/archive/command-workspace/", "/command/planning/", "/command/cases/", "/command/archive/", "/command/ver2/", "/command/exercise/", "/exercises/mae-sai-2024/injects.v1.json", "/planning-overlays/mae-sai-2024/se1.json", "/studio/", "/studio/planning-evidence/", "/studio/candidate-report/", "/studio/library/", "/studio/brief/", "/studio/archive/", EVIDENCE_CATALOG_ASSET]) {
  if (!serviceWorker.includes(`"${route}"`)) throw new Error(`Service worker does not precache ${route}`);
}
if (!serviceWorker.includes("requestUrl.origin !== self.location.origin")) {
  throw new Error("Service worker does not enforce same-origin runtime caching");
}
if (!serviceWorker.includes('event.request.mode === "navigate"') || !serviceWorker.includes("isMutableRequest")) {
  throw new Error("Service worker does not refresh mutable route documents network-first");
}
if (!serviceWorker.includes('fetch("/offline-assets.json", { cache: "no-store" })')) {
  throw new Error("Service worker can install from a stale offline asset manifest");
}
if (!serviceWorker.includes('fetch("/deployment-profile.json", { cache: "no-store" })')) {
  throw new Error("Service worker does not verify the deployed profile before populating its cache");
}
const generatedAssets = JSON.parse(readFileSync(resolve(out, "offline-assets.json"), "utf8"));
if (!Array.isArray(generatedAssets) || generatedAssets.length === 0) throw new Error("Production chunk manifest is empty");
for (const url of generatedAssets) {
  if (!url.startsWith("/_next/static/") || !existsSync(resolve(out, url.slice(1)))) {
    throw new Error(`Offline production chunk is invalid: ${url}`);
  }
}
// Landing artwork may be named in the worker's optional, deferred list; it must not be in the blocking one.
const mandatoryAssets = serviceWorker.match(/const CORE_ASSETS = (\[[^;]*\]);/)?.[1];
if (!mandatoryAssets || JSON.parse(mandatoryAssets).some((url) => url.startsWith("/landing/"))) {
  throw new Error("Optional landing imagery is part of the mandatory offline cache.");
}
const dynamicManifestPaths = [
  resolve(process.cwd(), ".next", "react-loadable-manifest.json"),
  resolve(process.cwd(), ".next", "server", "app", "page", "react-loadable-manifest.json"),
].filter((path) => existsSync(path));
for (const dynamicManifestPath of dynamicManifestPaths) {
  const dynamicManifest = JSON.parse(readFileSync(dynamicManifestPath, "utf8"));
  const directResources = new Set(routeFiles.flatMap((route) => (
    [...readFileSync(resolve(out, route), "utf8").matchAll(/<(?:script|link)\b[^>]*(?:src|href)="([^"?#]+)[^"]*"/gi)]
      .map((match) => match[1])
  )));
  for (const [name, entry] of Object.entries(dynamicManifest)) {
    const isNarrative = name.includes("narrative-canvas") || (entry.files ?? []).some((file) => (
      file.startsWith("static/") && file.endsWith(".js")
      && readFileSync(resolve(out, "_next", file), "utf8").includes("data-narrative-canvas")
    ));
    if (!isNarrative) continue;
    for (const file of entry.files ?? []) {
      const url = `/_next/${file}`;
      if (!directResources.has(url) && generatedAssets.includes(url)) {
        throw new Error(`Optional narrative renderer is mandatory offline: ${url}`);
      }
    }
  }
}

const bundle = JSON.parse(readFileSync(resolve(out, "offline-demo/bundle.json"), "utf8"));
if (bundle.status.dataset_mode !== "fixture_demo" || bundle.status.operational_status !== "non_operational" || bundle.status.official_warning !== false) {
  throw new Error("Offline bundle safety status is invalid");
}

const maeSaiBundle = JSON.parse(readFileSync(resolve(out, "offline-demo/mae-sai/bundle.json"), "utf8"));
const maeSaiManifest = JSON.parse(readFileSync(resolve(out, "offline-demo/mae-sai/manifest.json"), "utf8"));
if (maeSaiBundle.status.dataset_mode !== "candidate" || maeSaiBundle.status.study_area !== "mae_sai_candidate_v1" || maeSaiBundle.status.operational_status !== "non_operational" || maeSaiBundle.status.official_warning !== false) {
  throw new Error("Mae Sai offline bundle safety status is invalid");
}
if (maeSaiBundle.areas.length !== 8 || maeSaiManifest.layers.find((layer) => layer.layer_id === "road_risk")?.feature_count !== 4458 || maeSaiManifest.layers.find((layer) => layer.layer_id === "facilities")?.feature_count !== 42) {
  throw new Error("Mae Sai offline bundle feature contract is invalid");
}
if (maeSaiManifest.can_feed_decision_layer !== false || maeSaiManifest.official_warning !== false) {
  throw new Error("Mae Sai offline manifest does not fail closed");
}
const registryEntry = maeSaiBundle.model_registry?.[0]?.payload;
const modelRunV2 = maeSaiBundle.model_runs_v2?.[0];
const modelEvaluation = maeSaiBundle.model_evaluations?.[0];
const observationProduct = maeSaiBundle.observation_products?.[0];
const qualifiedFoundation = maeSaiBundle.qualified_evidence_foundation;
if (
  registryEntry?.source_bundle_sha256 !== maeSaiBundle.evidence_context.evidence_package_sha256
  || registryEntry?.evidence_kind !== "external_algorithmic_baseline"
  || registryEntry?.registry_status !== "blocked"
  || registryEntry?.permitted_use !== "report_only"
  || registryEntry?.can_feed_decision_layer !== false
  || modelRunV2?.run_id !== registryEntry?.model_run_id
  || modelRunV2?.run_status !== "blocked"
  || modelRunV2?.processing_allowed !== false
  || modelEvaluation?.evaluation_scope !== "not_evaluated"
  || observationProduct?.valid_coverage_fraction !== 0
  || observationProduct?.abstained_fraction !== 1
  || observationProduct?.counts_as_observed_evidence !== false
  || observationProduct?.can_feed_decision_layer !== false
) {
  throw new Error("Mae Sai offline Studio model evidence does not fail closed");
}
if (
  qualifiedFoundation?.schema_version !== "floodguard.qualified-evidence-foundation.v1"
  || qualifiedFoundation?.status !== "blocked"
  || qualifiedFoundation?.authoritative_receipt !== false
  || qualifiedFoundation?.source_timestamp !== "2026-07-23T12:24:48Z"
  || qualifiedFoundation?.reference_candidate_binding?.product_id !== "AIT-VAP001-TH"
  || qualifiedFoundation?.reference_candidate_binding?.qualification_status !== "blocked_external_permission_and_scientific_review"
  || qualifiedFoundation?.reference_candidate_binding?.processing_allowed !== false
  || qualifiedFoundation?.stages?.length !== 5
  || qualifiedFoundation?.permissions?.source_processing_allowed !== true
  || qualifiedFoundation?.permissions?.experiment_processing_allowed !== false
  || qualifiedFoundation?.permissions?.decision_layer_allowed !== false
  || qualifiedFoundation?.permissions?.operational_use_allowed !== false
  || qualifiedFoundation?.safety?.official_warning !== false
  || qualifiedFoundation?.safety?.can_feed_fpps !== false
) {
  throw new Error("Mae Sai qualified-evidence foundation does not fail closed");
}
if (
  !Array.isArray(maeSaiManifest.model_evidence_descriptors)
  || maeSaiManifest.model_evidence_descriptors.length !== 5
  || maeSaiManifest.model_evidence_descriptors.some(
    (item) => !existsSync(resolve(out, item.relative_url.replace(/^\//, ""))),
  )
) {
  throw new Error("Mae Sai model-evidence descriptors are not materialized.");
}
if (JSON.stringify(bundle).match(/(?:[A-Za-z]:[\\/](?:Users|home|private)[\\/]|\/(?:Users|home|private)\/)/i)) {
  throw new Error("Offline bundle contains a private absolute path");
}

// Case replay: the route is precached with the app; its data is a deferred, opt-in bucket derived from the
// timeline manifest at build time and verified by hash before the worker stores it.
const caseReplay = readCaseReplay(out);
const caseHtml = readFileSync(resolve(out, caseReplay.route.slice(1), "index.html"), "utf8");
for (const expected of [/Mae Sai flood, September 2024/, /not real-time, not an official warning/]) {
  if (!expected.test(caseHtml)) throw new Error(`Case-replay route lacks ${expected}`);
}
const caseResources = [...caseHtml.matchAll(/<(?:script|link)\b[^>]*(?:src|href)="([^"]+)"/gi)].map((match) => match[1]);
if (caseResources.some((url) => /^https?:\/\//i.test(url))) throw new Error("Case-replay route has external runtime resources");
if (!serviceWorker.includes(`"${caseReplay.route}"`)) throw new Error("Service worker does not precache the case-replay route");
const workerCaseReplay = serviceWorker.match(/const OPTIONAL_CASE_REPLAY = (\[[^;]*\]);/)?.[1];
if (!workerCaseReplay || JSON.stringify(JSON.parse(workerCaseReplay)) !== JSON.stringify(caseReplay.assets.map(({ url, sha256 }) => ({ url, sha256 })))) {
  throw new Error("Service worker's deferred case-replay files do not match the manifest inventory");
}
const workerCore = JSON.parse(serviceWorker.match(/const CORE_ASSETS = (\[[^;]*\]);/)?.[1] ?? "[]");
if (caseReplay.assets.some((asset) => workerCore.includes(asset.url))) throw new Error("Case-replay data was added to blocking installation");
if (!serviceWorker.includes('"FLOODGUARD_CACHE_CASE_REPLAY"') || !serviceWorker.includes('"FLOODGUARD_CASE_REPLAY_STATUS"')) {
  throw new Error("Service worker cannot save the case replay on request");
}
for (const asset of [...caseReplay.assets, ...caseReplay.exports.assets]) {
  const body = readFileSync(resolve(out, asset.url.slice(1)));
  if (createHash("sha256").update(body).digest("hex") !== asset.sha256 || body.byteLength !== asset.bytes) {
    throw new Error(`Case-replay file differs from its manifest: ${asset.url}`);
  }
}
// The export pack (download files) is a second deferred list with its own byte total: never in the blocking
// installation, never in the replay's precache set, and saved by the same request as the replay data.
const workerCaseReplayExports = serviceWorker.match(/const OPTIONAL_CASE_REPLAY_EXPORTS = (\[[^;]*\]);/)?.[1];
if (!workerCaseReplayExports || JSON.stringify(JSON.parse(workerCaseReplayExports)) !== JSON.stringify(caseReplay.exports.assets.map(({ url, sha256 }) => ({ url, sha256 })))) {
  throw new Error("Service worker's case-replay export files do not match the manifest inventory");
}
if (caseReplay.exports.assets.length === 0) throw new Error("The case replay ships no export pack");
if (caseReplay.exports.assets.some((asset) => workerCore.includes(asset.url) || caseReplay.assets.some((data) => data.url === asset.url))) {
  throw new Error("A case-replay export file was added to blocking installation or to the replay's precache set");
}
if (caseReplay.exports.bytes > caseReplay.exports.budget_bytes) throw new Error("The case-replay export pack is over its budget");

// Evidence library: only its catalogue is in the blocking installation. Each study area (package files, terrain
// preview, the shared report) is a deferred bucket the worker saves when a page asks (the reader opened the area, or
// pressed its save button), pinned by SHA-256; the database archives offered for download are never kept by the worker.
const evidenceLibrary = auditEvidenceLibrary(out);
const workerEvidenceAreas = readWorkerEvidenceAreas(serviceWorker);
if (evidenceLibrary.areas.length === 0 || JSON.stringify(workerEvidenceAreas) !== JSON.stringify(evidenceLibrary.areas)) {
  throw new Error("Service worker's study-area lists do not match the published evidence library");
}
if (!workerCore.includes(EVIDENCE_CATALOG_ASSET)) throw new Error("The evidence library's catalogue is not part of the blocking installation");
const libraryInCore = workerCore.filter((url) => url.startsWith("/evidence-library/") && url !== EVIDENCE_CATALOG_ASSET);
if (libraryInCore.length > 0) throw new Error(`Evidence-library files were added to blocking installation: ${libraryInCore.join(", ")}`);
const evidenceAreaFiles = new Map(evidenceLibrary.areas.flatMap((area) => area.assets.map((asset) => [asset.url, asset])));
for (const [url, asset] of evidenceAreaFiles) {
  const body = readFileSync(resolve(out, url.slice(1)));
  if (createHash("sha256").update(body).digest("hex") !== asset.sha256 || body.byteLength !== asset.bytes) {
    throw new Error(`Study-area file differs from its pinned hash or size: ${url}`);
  }
}
for (const reference of JSON.parse(readFileSync(resolve(out, EVIDENCE_CATALOG_ASSET.slice(1)), "utf8")).packages) {
  // The hash the worker checks is the one the catalogue pins and the page checks again.
  if (evidenceAreaFiles.get(reference.url)?.sha256 !== reference.sha256) throw new Error(`Study-area list does not pin the catalogue's hash: ${reference.id}`);
}
for (const archive of evidenceLibrary.onlineOnly) {
  if (serviceWorker.includes(`"${archive.url}"`)) throw new Error(`A database archive is named in the service worker: ${archive.url}`);
}
for (const message of ["FLOODGUARD_SAVE_EVIDENCE_AREA", "FLOODGUARD_REMOVE_EVIDENCE_AREA", "FLOODGUARD_EVIDENCE_AREAS_STATUS_REQUEST", "FLOODGUARD_EVIDENCE_AREA_STATUS"]) {
  if (!serviceWorker.includes(`"${message}"`)) throw new Error(`Service worker cannot handle ${message}`);
}
if (!serviceWorker.includes(`const EVIDENCE_AREA_CACHE = "${EVIDENCE_AREA_CACHE}";`) || /^floodguard-offline-/.test(EVIDENCE_AREA_CACHE)) {
  throw new Error("Saved study areas must live in a cache of their own, outside the per-build cache");
}
// Hard budget of the blocking installation (12 MB): CORE_ASSETS plus the generated chunk list, as built.
const install = verifyOfflineInstall(out);
const evidenceAreaBytes = [...evidenceAreaFiles.values()].reduce((sum, asset) => sum + asset.bytes, 0);

const proposalEvidencePath = resolve(out, "proposal-evidence.json");
if (existsSync(proposalEvidencePath)) {
  const proposalEvidence = JSON.parse(readFileSync(proposalEvidencePath, "utf8"));
  const serialized = JSON.stringify(proposalEvidence);
  if (/(?:[A-Za-z]:[\\/]|file:\/\/|\/(?:Users|home|root|tmp|var|opt|mnt|srv)\/)/i.test(serialized)) {
    throw new Error("Proposal evidence contains a private absolute path");
  }
  if (proposalEvidence.dataset_mode !== "official_input" && proposalEvidence.geoai_proof?.can_feed_decision_layer !== false) {
    throw new Error("Proposal evidence does not fail closed for fixture/candidate data");
  }
  if (!serviceWorker.includes('"/proposal-evidence.json"')) {
    throw new Error("Proposal evidence is not included in the offline cache");
  }
}

console.log(`offline smoke: ${routeFiles.length} polished routes and ${requiredPublicAssets.length} core assets verified; /command/planning/ (as built, before a case loads) and the three forwards show none of the written forms of a research score or class, /studio/archive/command-workspace/ its ${workspace.rows.length} retained rows with the bundle's values and classes (rail and map list) and no other one-decimal number, under its label; case replay route precached with ${caseReplay.assets.length} deferred data files (${(caseReplay.bytes / 1e6).toFixed(1)} MB, opt-in) and ${caseReplay.exports.assets.length} export files (${(caseReplay.exports.bytes / 1e6).toFixed(2)} MB of a ${(caseReplay.exports.budget_bytes / 1e6).toFixed(1)} MB export budget); blocking installation ${install.files} files, ${megabytes(install.bytes)} of ${megabytes(install.budget_bytes)} MB budget (${install.bytes} bytes); evidence library: catalogue precached, ${evidenceLibrary.areas.length} study areas saved when opened or on request (${megabytes(evidenceAreaBytes)} MB in ${evidenceAreaFiles.size} files, largest area ${megabytes(Math.max(...evidenceLibrary.areas.map((area) => area.bytes)))} MB), ${evidenceLibrary.onlineOnly.length} database archives online only (${megabytes(evidenceLibrary.onlineOnly.reduce((sum, asset) => sum + asset.bytes, 0))} MB); internal safety contracts retained and no external runtime resources`);
