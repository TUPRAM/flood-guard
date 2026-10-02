import { existsSync, readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { resolve } from "node:path";

import { readCaseReplay } from "./case-replay-inventory.mjs";

const out = resolve(process.cwd(), "out");
const routeFiles = ["index.html", "public/index.html", "command/index.html", "studio/index.html", "studio/planning-evidence/index.html"];
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
  "command/index.html": [
    /Planning intelligence|ข้อมูลเพื่อการวางแผน/i,
    /Source time|เวลาข้อมูล/i,
    /Confidence|ความเชื่อมั่น/i,
    /DDPM|ปภ\./i,
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
  !/floodguard-offline-[0-9a-f]{12}/.test(serviceWorker)
) {
  throw new Error("Service worker does not use a content-derived cache version");
}
for (const route of ["/", "/public/", "/command/", "/studio/", "/studio/planning-evidence/"]) {
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

console.log(`offline smoke: ${routeFiles.length} polished routes and ${requiredPublicAssets.length} core assets verified; case replay route precached with ${caseReplay.assets.length} deferred data files (${(caseReplay.bytes / 1e6).toFixed(1)} MB, opt-in) and ${caseReplay.exports.assets.length} export files (${(caseReplay.exports.bytes / 1e6).toFixed(2)} MB of a ${(caseReplay.exports.budget_bytes / 1e6).toFixed(1)} MB export budget); internal safety contracts retained and no external runtime resources`);
