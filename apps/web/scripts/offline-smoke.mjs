import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const out = resolve(process.cwd(), "out");
const routeFiles = ["index.html", "public/index.html", "command/index.html", "studio/index.html"];
const requiredPublicAssets = [
  "manifest.webmanifest",
  "sw.js",
  "icon.svg",
  "offline-demo/bundle.json",
  "offline-demo/areas.geojson",
  "offline-demo/roads.geojson",
  "offline-demo/context.geojson",
  "proposal-evidence-status.json",
  "offline-assets.json",
];

for (const relative of [...routeFiles, ...requiredPublicAssets]) {
  const path = resolve(out, relative);
  if (!existsSync(path)) throw new Error(`Offline artifact missing: ${relative}`);
}

for (const relative of routeFiles) {
  const html = readFileSync(resolve(out, relative), "utf8");
  if (!/Fixture demo|ข้อมูลสาธิต/.test(html)) {
    throw new Error(`${relative} lacks a fixture-mode disclosure`);
  }
  if (!/Non-operational|ไม่ใช่ระบบปฏิบัติการ/.test(html)) {
    throw new Error(`${relative} lacks a non-operational disclosure`);
  }
  const resourceUrls = [...html.matchAll(/<(?:script|link)\b[^>]*(?:src|href)="([^"]+)"/gi)].map((match) => match[1]);
  const external = resourceUrls.filter((url) => /^https?:\/\//i.test(url));
  if (external.length) throw new Error(`${relative} has external runtime resources: ${external.join(", ")}`);
}

const serviceWorker = readFileSync(resolve(out, "sw.js"), "utf8");
if (serviceWorker.includes("__BUILD__") || serviceWorker.includes("__PROPOSAL_EVIDENCE_ASSETS__") || !/floodguard-offline-[0-9a-f]{12}/.test(serviceWorker)) {
  throw new Error("Service worker does not use a content-derived cache version");
}
for (const route of ["/public/", "/command/", "/studio/"]) {
  if (!serviceWorker.includes(`"${route}"`)) throw new Error(`Service worker does not precache ${route}`);
}
if (!serviceWorker.includes("requestUrl.origin !== self.location.origin")) {
  throw new Error("Service worker does not enforce same-origin runtime caching");
}
if (!serviceWorker.includes('event.request.mode === "navigate"') || !serviceWorker.includes("isMutableRequest")) {
  throw new Error("Service worker does not refresh mutable route documents network-first");
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
if (JSON.stringify(bundle).match(/(?:[A-Za-z]:[\\/](?:Users|home|private)[\\/]|\/(?:Users|home|private)\/)/i)) {
  throw new Error("Offline bundle contains a private absolute path");
}

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

console.log(`offline smoke: ${routeFiles.length} routes and ${requiredPublicAssets.length} core assets verified; no external runtime resources`);
