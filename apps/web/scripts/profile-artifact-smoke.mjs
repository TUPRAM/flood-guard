import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { relative, resolve, sep } from "node:path";

const requested = process.argv[2]?.trim().toLowerCase();
const profile = requested === "public" || requested === "public-production"
  ? "public-production"
  : requested === "competition"
    ? "competition"
    : null;
if (!profile) throw new Error("Usage: node scripts/profile-artifact-smoke.mjs competition|public-production");

const out = resolve(process.cwd(), "out");
const deployment = readJson("deployment-profile.json");
if (deployment.profile !== profile) throw new Error(`Deployment profile mismatch: expected ${profile}, received ${deployment.profile}`);
const expectedSurfaces = profile === "competition" ? ["public", "command", "studio"] : ["public"];
if (JSON.stringify(deployment.included_surfaces) !== JSON.stringify(expectedSurfaces)) {
  throw new Error(`Unexpected surfaces for ${profile}: ${JSON.stringify(deployment.included_surfaces)}`);
}

const serviceWorker = readText("sw.js");
for (const token of ["__BUILD__", "__APP_PROFILE__", "__CACHE_CREATED_AT__", "__PROFILE_CORE_ASSETS__"]) {
  if (serviceWorker.includes(token)) throw new Error(`Finalized service worker retains ${token}`);
}
if (!serviceWorker.includes(`const APP_PROFILE = "${profile}"`)) throw new Error("Service worker profile is incorrect.");
if (!serviceWorker.includes('fetch("/offline-assets.json", { cache: "no-store" })')) {
  throw new Error("Service worker can install from a stale offline asset manifest.");
}
if (!serviceWorker.includes('fetch("/deployment-profile.json", { cache: "no-store" })')) {
  throw new Error("Service worker does not verify the deployed profile before populating its cache.");
}

const offlineAssets = readJson("offline-assets.json");
if (!Array.isArray(offlineAssets) || offlineAssets.length === 0) throw new Error("Offline production dependency list is empty.");
for (const asset of offlineAssets) {
  if (typeof asset !== "string" || !asset.startsWith("/_next/static/") || !existsSync(resolve(out, asset.slice(1)))) {
    throw new Error(`Invalid offline dependency: ${asset}`);
  }
}

for (const required of [
  "index.html",
  "public/index.html",
  "offline-demo/mae-sai/public-bundle.json",
  "offline-demo/mae-sai/public-areas.json",
]) {
  requirePath(required);
}

validatePublicProjection();

if (profile === "public-production") {
  validatePublicProduction();
} else {
  validateCompetition();
}

console.log(`deployment profile smoke: ${profile} artifact, routes, evidence payloads, cache inventory, and shipped-text boundary verified`);

function validatePublicProduction() {
  if (deployment.staff_access !== "not_deployed" || deployment.cache_policy !== "public_projection_only") {
    throw new Error("Public deployment policy does not fail closed.");
  }
  for (const excluded of [
    "command",
    "studio",
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
    "offline-demo/mae-sai/model-evidence",
    "proposal-evidence.json",
    "proposal-evidence-assets",
  ]) {
    if (existsSync(resolve(out, excluded))) throw new Error(`Public profile shipped excluded artifact: ${excluded}`);
  }

  const rootHtml = readText("index.html");
  if (!/Public preparedness|การเตรียมพร้อมรับน้ำท่วม/i.test(rootHtml)) throw new Error("Public root does not render the Public experience.");
  if (/One platform\. Three planning views|href="\/command\/?"|href="\/studio\/?"/i.test(rootHtml)) {
    throw new Error("Public root retains competition or staff navigation.");
  }
  for (const forbidden of [
    "/offline-demo/mae-sai/roads.json",
    "/offline-demo/mae-sai/facilities.json",
    "/offline-demo/mae-sai/access-hotspots.json",
    "/offline-demo/bundle.json",
    "/api/v1/scenario-runs",
    "OSM-11566575669",
    "synthetic-sar-baseline-v1",
    "mae-sai-2024-model-evaluation-blocked",
    "geoai-synthetic-proof-001-report-only-product",
  ]) {
    const hit = scanTextArtifacts(forbidden);
    if (hit) throw new Error(`Public profile contains staff-only sentinel ${JSON.stringify(forbidden)} in ${hit}`);
    if (serviceWorker.includes(forbidden)) throw new Error(`Public service-worker cache inventory contains ${forbidden}`);
  }
  for (const route of ["/command/", "/studio/"]) {
    if (serviceWorker.includes(`"${route}"`)) throw new Error(`Public cache list contains staff route ${route}`);
  }
}

function validateCompetition() {
  if (deployment.staff_access !== "presentation_boundary_only" || deployment.cache_policy !== "competition_open_evidence") {
    throw new Error("Competition deployment policy is incorrect.");
  }
  for (const required of [
    "command/index.html",
    "studio/index.html",
    "offline-demo/bundle.json",
    "offline-demo/mae-sai/bundle.json",
    "offline-demo/mae-sai/roads.json",
    "offline-demo/mae-sai/facilities.json",
    "offline-demo/mae-sai/access-hotspots.json",
  ]) requirePath(required);
  const rootHtml = readText("index.html");
  if (!/One platform\. Three planning views/i.test(rootHtml)) throw new Error("Competition root chooser is missing.");
  for (const route of ["/", "/public/", "/command/", "/studio/"]) {
    if (!serviceWorker.includes(`"${route}"`)) throw new Error(`Competition cache list omits ${route}`);
  }
  const bundle = readJson("offline-demo/mae-sai/bundle.json");
  if (
    !Array.isArray(bundle.model_registry)
    || bundle.model_registry.length !== 1
    || !Array.isArray(bundle.model_runs_v2)
    || bundle.model_runs_v2.length !== 1
    || !Array.isArray(bundle.model_evaluations)
    || bundle.model_evaluations.length !== 1
    || !Array.isArray(bundle.observation_products)
    || bundle.observation_products.length !== 1
  ) {
    throw new Error("Competition profile is missing the complete Studio model-evidence chain.");
  }
  const entry = bundle.model_registry[0]?.payload;
  const modelRun = bundle.model_runs_v2[0];
  const evaluation = bundle.model_evaluations[0];
  const product = bundle.observation_products[0];
  if (
    entry?.source_bundle_sha256 !== bundle.evidence_context.evidence_package_sha256
    || entry?.evidence_kind !== "external_algorithmic_baseline"
    || entry?.registry_status !== "blocked"
    || entry?.permitted_use !== "report_only"
    || entry?.can_feed_decision_layer !== false
    || entry?.official_warning !== false
    || modelRun?.run_id !== entry?.model_run_id
    || modelRun?.run_status !== "blocked"
    || evaluation?.evaluation_scope !== "not_evaluated"
    || product?.valid_coverage_fraction !== 0
    || product?.abstained_fraction !== 1
    || product?.counts_as_observed_evidence !== false
    || product?.can_feed_decision_layer !== false
  ) {
    throw new Error("Competition Studio model evidence does not preserve its fail-closed boundary.");
  }
  const descriptorPaths = Object.keys(bundle.model_asset_descriptors ?? {});
  if (descriptorPaths.length !== 5) {
    throw new Error("Competition Studio model descriptors are incomplete.");
  }
  for (const relativePath of descriptorPaths) requirePath(relativePath);
}

function validatePublicProjection() {
  const bundle = readJson("offline-demo/mae-sai/public-bundle.json");
  const allowedBundleKeys = ["evidence_context", "evidence_record", "hotlines", "layers", "public_areas", "shelters", "status"];
  assertExactKeys(bundle, allowedBundleKeys, "public bundle");
  if (!Array.isArray(bundle.public_areas) || bundle.public_areas.length !== 8) throw new Error("Public bundle must contain eight reduced area records.");
  if (!Array.isArray(bundle.shelters) || bundle.shelters.length !== 0) throw new Error("Public bundle must not publish an unverified shelter.");
  const featureCollection = readJson("offline-demo/mae-sai/public-areas.json");
  if (featureCollection.type !== "FeatureCollection" || !Array.isArray(featureCollection.features) || featureCollection.features.length !== 8) {
    throw new Error("Public area projection is not the expected eight-feature collection.");
  }
  const allowedProperties = [
    "area_id",
    "area_name_en",
    "area_name_th",
    "current_conditions_confirmed",
    "evidence_context_id",
    "evidence_sufficiency",
    "freshness",
    "planning_priority_0_100",
    "recommendation_code",
    "schema_version",
    "source_timestamp",
  ];
  for (const feature of featureCollection.features) assertExactKeys(feature.properties, allowedProperties, `public area ${feature.properties?.area_id ?? "unknown"}`);
  const serialized = JSON.stringify({ bundle, featureCollection });
  for (const forbidden of ["candidate_evidence", "fpps_0_100", "scenario_results", "people_losing_30_min_access", "roadFeatures", "facilityFeatures", "accessFeatures"]) {
    if (serialized.includes(`"${forbidden}"`)) throw new Error(`Public projection includes staff field ${forbidden}`);
  }
}

function assertExactKeys(value, expected, label) {
  const actual = Object.keys(value ?? {}).sort();
  const sortedExpected = [...expected].sort();
  if (JSON.stringify(actual) !== JSON.stringify(sortedExpected)) {
    throw new Error(`${label} properties differ: ${JSON.stringify(actual)}`);
  }
}

function scanTextArtifacts(needle) {
  for (const path of walk(out)) {
    if (!/\.(?:html|js|json|txt)$/i.test(path)) continue;
    if (readFileSync(path, "utf8").includes(needle)) return relative(out, path).split(sep).join("/");
  }
  return null;
}

function walk(directory) {
  return readdirSync(directory).flatMap((name) => {
    const path = resolve(directory, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

function requirePath(relativePath) {
  if (!existsSync(resolve(out, relativePath))) throw new Error(`Profile artifact is missing: ${relativePath}`);
}

function readText(relativePath) {
  return readFileSync(resolve(out, relativePath), "utf8");
}

function readJson(relativePath) {
  return JSON.parse(readText(relativePath));
}
