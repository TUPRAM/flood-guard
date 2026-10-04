import { createHash } from "node:crypto";
import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, relative, resolve, sep } from "node:path";
import { CASE_REPLAY_EXPORT_BUDGET_BYTES, CASE_REPLAY_ROUTE, caseReplayExportBytes, collectCaseReplay, readCaseReplayExports } from "./case-replay-inventory.mjs";
import { collectLandingArtwork } from "./landing-artwork-inventory.mjs";
import { auditEvidenceLibrary, EVIDENCE_CATALOG_ASSET } from "./evidence-library-assets.mjs";
import { megabytes, offlineInstallBytes } from "./offline-install-budget.mjs";
import { collectPublicCaseAssets } from "./public-case-assets.mjs";
import { collectCaseBriefAssets } from "./case-brief-assets.mjs";

const out = resolve(process.cwd(), "out");
const nextStatic = resolve(out, "_next", "static");
const appProfile = resolveAppProfile(process.env.FLOODGUARD_APP_PROFILE ?? process.env.NEXT_PUBLIC_FLOODGUARD_APP_PROFILE);

if (appProfile === "public-production") prunePublicProductionOutput();
const optionalArtwork = appProfile === "competition" ? collectLandingArtwork(out) : [];
// The case replay's data is a deferred, opt-in bucket (see case-replay-inventory.mjs): derived from its
// manifest here, cached only after the replay page asks, never part of the blocking installation.
const optionalCaseReplay = appProfile === "competition" ? collectCaseReplay(out) : [];
// The replay's export pack (download files) is listed apart from the replay data, hash-verified against the
// manifest and held to its own budget: it is outside the replay's precache budget.
const optionalCaseReplayExports = appProfile === "competition" ? readCaseReplayExports(out) : [];
const caseReplayExportTotal = caseReplayExportBytes(optionalCaseReplayExports);
// Historical user-supplied aerial references are not approved publication assets.
for (const name of ["hero-desktop.webp", "hero-mobile.webp"]) {
  rmSync(resolve(out, "landing", name), { force: true });
}

function walk(directory) {
  return readdirSync(directory).flatMap((name) => {
    const path = resolve(directory, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

const optionalLandingAssets = collectOptionalLandingAssets();
const assets = walk(nextStatic)
  .map((path) => `/${relative(out, path).split(sep).join("/")}`)
  .filter((url) => !optionalLandingAssets.has(url))
  .sort();

writeFileSync(resolve(out, "offline-assets.json"), `${JSON.stringify(assets, null, 2)}\n`, "utf8");

if (appProfile === "competition") copyCanonicalProposalEvidence();
const proposalEvidenceAssets = appProfile === "competition" ? collectProposalEvidenceAssets() : [];
// The evidence library: the whole published set is audited here, but only its catalogue joins the blocking
// installation. Each study area is an opt-in bucket (package files, terrain preview and the shared report, pinned by
// SHA-256), saved when the reader asks on the area's page; its database archives are never kept by the worker.
const evidenceLibrary = appProfile === "competition" ? auditEvidenceLibrary(out) : { urls: [], areas: [], onlineOnly: [] };
const optionalEvidenceAreas = evidenceLibrary.areas;
const evidenceCoreAssets = appProfile === "competition" ? [EVIDENCE_CATALOG_ASSET] : [];
const publicCaseAssets = appProfile === "competition" ? collectPublicCaseAssets(out) : [];
const caseBriefAssets = appProfile === "competition" ? collectCaseBriefAssets(out) : [];
const publicCoreAssets = [
  "/",
  "/public/",
  "/manifest.webmanifest",
  "/floodguard-logo.png",
  "/flood-height.png",
  "/deployment-profile.json",
  "/offline-demo/mae-sai/public-bundle.json",
  "/offline-demo/mae-sai/public-areas.json",
];
const coreAssets = appProfile === "public-production"
  ? publicCoreAssets
  : [
      ...publicCoreAssets,
      "/policy/",
      "/command/",
      "/command/archive/",
      "/studio/",
      "/studio/planning-evidence/",
      CASE_REPLAY_ROUTE,
      "/studio/candidate-report/",
      "/studio/library/",
      "/studio/brief/",
      "/studio/archive/",
      "/public-cases/",
      "/command/cases/",
      "/offline-demo/bundle.json",
      "/offline-demo/areas.geojson",
      "/offline-demo/roads.geojson",
      "/offline-demo/context.geojson",
      "/offline-demo/mae-sai/bundle.json",
      "/offline-demo/mae-sai/manifest.json",
      "/offline-demo/mae-sai/areas.json",
      "/offline-demo/mae-sai/roads.json",
      "/offline-demo/mae-sai/facilities.json",
      "/offline-demo/mae-sai/access-hotspots.json",
      ...proposalEvidenceAssets,
      ...evidenceCoreAssets,
      ...publicCaseAssets,
      ...caseBriefAssets,
    ];
const blocked = coreAssets.filter((url) => optionalEvidenceAreas.some((area) => area.assets.some((asset) => asset.url === url))
  || evidenceLibrary.onlineOnly.some((asset) => asset.url === url));
if (blocked.length > 0) throw new Error(`Study-area files were added to the blocking installation: ${blocked.join(", ")}`);
const deploymentProfile = {
  profile: appProfile,
  entry: "/",
  included_surfaces: appProfile === "competition" ? ["public", "command", "studio"] : ["public"],
  staff_access: appProfile === "competition" ? "presentation_boundary_only" : "not_deployed",
  cache_policy: appProfile === "competition" ? "competition_open_evidence" : "public_projection_only",
};
writeFileSync(resolve(out, "deployment-profile.json"), `${JSON.stringify(deploymentProfile, null, 2)}\n`, "utf8");

// Hard budget of the blocking installation (offline-install-budget.mjs): the build fails above 12 MB, before the
// service worker is finalized.
const install = offlineInstallBytes(out, coreAssets, assets);

const versionedFiles = [
  ...assets.map((path) => resolve(out, path.slice(1))),
  resolve(out, "index.html"),
  resolve(out, "public", "index.html"),
  resolve(out, "manifest.webmanifest"),
  resolve(out, "floodguard-logo.png"),
  resolve(out, "flood-height.png"),
  resolve(out, "deployment-profile.json"),
  resolve(out, "offline-demo", "mae-sai", "public-bundle.json"),
  resolve(out, "offline-demo", "mae-sai", "public-areas.json"),
  ...(appProfile === "competition" ? [
    resolve(out, "policy", "index.html"),
    resolve(out, "command", "index.html"),
    resolve(out, "command", "archive", "index.html"),
    resolve(out, "command", "cases", "index.html"),
    resolve(out, "public-cases", "index.html"),
    resolve(out, "studio", "index.html"),
    resolve(out, "studio", "planning-evidence", "index.html"),
    resolve(out, CASE_REPLAY_ROUTE.slice(1), "index.html"),
    resolve(out, "studio", "candidate-report", "index.html"),
    resolve(out, "studio", "library", "index.html"),
    resolve(out, "studio", "brief", "index.html"),
    resolve(out, "studio", "archive", "index.html"),
    resolve(out, "offline-demo", "bundle.json"),
    resolve(out, "offline-demo", "areas.geojson"),
    resolve(out, "offline-demo", "roads.geojson"),
    resolve(out, "offline-demo", "context.geojson"),
    resolve(out, "offline-demo", "mae-sai", "bundle.json"),
    resolve(out, "offline-demo", "mae-sai", "manifest.json"),
    resolve(out, "offline-demo", "mae-sai", "areas.json"),
    resolve(out, "offline-demo", "mae-sai", "roads.json"),
    resolve(out, "offline-demo", "mae-sai", "facilities.json"),
    resolve(out, "offline-demo", "mae-sai", "access-hotspots.json"),
  ] : []),
  ...proposalEvidenceAssets.map((url) => resolve(out, url.slice(1))),
  ...optionalArtwork.map((asset) => resolve(out, asset.url.slice(1))),
  ...optionalCaseReplay.map((asset) => resolve(out, asset.url.slice(1))),
  ...optionalCaseReplayExports.map((asset) => resolve(out, asset.url.slice(1))),
  // Study-area files are versioned by the hashes in their list (below), not by reading 290 MB again.
  ...evidenceCoreAssets.map((url) => resolve(out, url.slice(1))),
  ...publicCaseAssets.map((url) => resolve(out, url.slice(1))),
  ...caseBriefAssets.map((url) => resolve(out, url.slice(1))),
];
const serviceWorkerPath = resolve(out, "sw.js");
const serviceWorker = readFileSync(serviceWorkerPath, "utf8");
const buildHash = createHash("sha256");
for (const path of versionedFiles) {
  buildHash.update(relative(out, path).split(sep).join("/"));
  buildHash.update(readFileSync(path));
}
buildHash.update("service-worker-policy");
buildHash.update(serviceWorker);
buildHash.update(JSON.stringify(deploymentProfile));
buildHash.update(JSON.stringify(coreAssets));
buildHash.update(JSON.stringify(optionalArtwork));
buildHash.update(JSON.stringify(optionalCaseReplay));
buildHash.update(JSON.stringify(optionalCaseReplayExports));
buildHash.update(JSON.stringify(optionalEvidenceAreas));
buildHash.update(JSON.stringify(evidenceLibrary.onlineOnly));
const cacheVersion = buildHash.digest("hex").slice(0, 12);
const cacheCreatedAt = new Date().toISOString();
if (!serviceWorker.includes("__BUILD__") || !serviceWorker.includes("__APP_PROFILE__") || !serviceWorker.includes("__CACHE_CREATED_AT__") || !serviceWorker.includes("__PROFILE_CORE_ASSETS__") || !serviceWorker.includes("__OPTIONAL_LANDING_ARTWORK__") || !serviceWorker.includes("__OPTIONAL_CASE_REPLAY__") || !serviceWorker.includes("__OPTIONAL_CASE_REPLAY_EXPORTS__") || !serviceWorker.includes("__OPTIONAL_EVIDENCE_AREAS__")) {
  throw new Error("Service-worker build tokens are missing.");
}
writeFileSync(
  serviceWorkerPath,
  serviceWorker
    .replaceAll("__BUILD__", cacheVersion)
    .replaceAll("__APP_PROFILE__", appProfile)
    .replaceAll("__CACHE_CREATED_AT__", cacheCreatedAt)
    .replace("const OPTIONAL_LANDING_ARTWORK = []; /* __OPTIONAL_LANDING_ARTWORK__ */", `const OPTIONAL_LANDING_ARTWORK = ${JSON.stringify(optionalArtwork)};`)
    .replace(
      "const OPTIONAL_CASE_REPLAY = []; /* __OPTIONAL_CASE_REPLAY__ */",
      `const OPTIONAL_CASE_REPLAY = ${JSON.stringify(optionalCaseReplay.map(({ url, sha256 }) => ({ url, sha256 })))};`,
    )
    .replace(
      "const OPTIONAL_CASE_REPLAY_EXPORTS = []; /* __OPTIONAL_CASE_REPLAY_EXPORTS__ */",
      `const OPTIONAL_CASE_REPLAY_EXPORTS = ${JSON.stringify(optionalCaseReplayExports.map(({ url, sha256 }) => ({ url, sha256 })))};`,
    )
    .replace(
      "const OPTIONAL_EVIDENCE_AREAS = []; /* __OPTIONAL_EVIDENCE_AREAS__ */",
      `const OPTIONAL_EVIDENCE_AREAS = ${JSON.stringify(optionalEvidenceAreas)};`,
    )
    .replace(
      "const CORE_ASSETS = []; /* __PROFILE_CORE_ASSETS__ */",
      `const CORE_ASSETS = ${JSON.stringify(coreAssets)};`,
    ),
  "utf8",
);

const installLine = `blocking install ${install.files} files, ${megabytes(install.bytes)} of ${megabytes(install.budget_bytes)} MB budget (${install.bytes} bytes)`;
const evidenceAreaBytes = new Map(optionalEvidenceAreas.flatMap((area) => area.assets.map((asset) => [asset.url, asset.bytes])));
const evidenceAreaLine = `${optionalEvidenceAreas.length} study areas saved on request (${megabytes([...evidenceAreaBytes.values()].reduce((sum, bytes) => sum + bytes, 0))} MB in ${evidenceAreaBytes.size} files), ${evidenceLibrary.onlineOnly.length} database archives online only (${megabytes(evidenceLibrary.onlineOnly.reduce((sum, asset) => sum + asset.bytes, 0))} MB)`;
// Decimal megabytes, the unit of the replay's 6.5 MB precache budget (case-replay-inventory.mjs).
const caseReplayMegabytes = (optionalCaseReplay.reduce((sum, asset) => sum + asset.bytes, 0) / 1e6).toFixed(1);
// The export pack has its own budget line (decimal megabytes), outside the precache budget.
const caseReplayExportLine = `${optionalCaseReplayExports.length} case-replay export files (${caseReplayExportTotal} of ${CASE_REPLAY_EXPORT_BUDGET_BYTES} export-budget bytes, outside the precache budget)`;
console.log(`offline asset manifest: ${assets.length} production chunks, ${optionalLandingAssets.size} optional landing chunks excluded, ${proposalEvidenceAssets.length} proposal evidence assets, ${optionalArtwork.length} deferred illustration assets, ${optionalCaseReplay.length} deferred case-replay files (${caseReplayMegabytes} MB, opt-in), ${caseReplayExportLine}, ${evidenceAreaLine}; ${installLine}; profile ${appProfile}; cache ${cacheVersion}`);

function collectOptionalLandingAssets() {
  const manifestPath = resolve(process.cwd(), ".next", "react-loadable-manifest.json");
  const appManifests = resolve(process.cwd(), ".next", "server", "app");
  const manifests = [
    ...(existsSync(manifestPath) ? [manifestPath] : []),
    ...(existsSync(appManifests) ? walk(appManifests).filter((path) => path.endsWith(`${sep}react-loadable-manifest.json`)) : []),
  ];
  const optional = new Set();
  for (const path of manifests) {
    const manifest = JSON.parse(readFileSync(path, "utf8"));
    for (const [name, entry] of Object.entries(manifest)) {
      const files = Array.isArray(entry?.files) ? entry.files : [];
      const isNarrative = name.includes("narrative-canvas") || files.some((file) => {
        if (typeof file !== "string" || !file.startsWith("static/") || !file.endsWith(".js")) return false;
        const chunkPath = resolve(out, "_next", file);
        return chunkPath.startsWith(`${nextStatic}${sep}`) && existsSync(chunkPath)
          && readFileSync(chunkPath, "utf8").includes("data-narrative-canvas");
      });
      if (!isNarrative) continue;
      for (const file of files) {
        if (typeof file === "string" && file.startsWith("static/")) optional.add(`/_next/${file}`);
      }
    }
  }
  if (appProfile === "public-production") {
    for (const path of walk(nextStatic)) {
      if (!path.endsWith(".js")) continue;
      const source = readFileSync(path, "utf8");
      if (source.includes("floodguard:landing-motion:v1") || source.includes("data-narrative-canvas")) {
        optional.add(`/${relative(out, path).split(sep).join("/")}`);
      }
    }
  }
  // A shared dependency referenced by a route remains mandatory even if the
  // optional canvas also appears in its dynamic-import dependency manifest.
  for (const route of ["index.html", "public/index.html", "command/index.html", "studio/index.html", "studio/library/index.html", "studio/brief/index.html"]) {
    const path = resolve(out, route);
    if (!existsSync(path)) continue;
    const html = readFileSync(path, "utf8");
    for (const match of html.matchAll(/<(?:script|link)\b[^>]*(?:src|href)="([^"?#]+)[^"]*"/gi)) {
      optional.delete(match[1]);
    }
  }
  return optional;
}

function resolveAppProfile(value) {
  const normalized = value?.trim().toLowerCase();
  if (!normalized || normalized === "competition") return "competition";
  if (normalized === "public" || normalized === "public-production") return "public-production";
  throw new Error(`Unsupported FloodGuard deployment profile: ${value}`);
}

function prunePublicProductionOutput() {
  const excluded = [
    "landing",
    "policy",
    "command",
    "studio",
    "studies",
    "evidence-library",
    "public-case-projections",
    "briefs",
    "public-cases",
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
    "offline-case-replay.json",
  ];
  for (const relativePath of excluded) {
    const target = resolve(out, relativePath);
    if (!target.startsWith(`${out}${sep}`)) throw new Error(`Refusing to prune outside build output: ${relativePath}`);
    if (existsSync(target)) rmSync(target, { recursive: true, force: true });
  }
}

function collectProposalEvidenceAssets() {
  const manifestPath = resolve(out, "proposal-evidence.json");
  const statusPath = resolve(out, "proposal-evidence-status.json");
  const available = existsSync(manifestPath);
  writeFileSync(statusPath, `${JSON.stringify({ available }, null, 2)}\n`, "utf8");
  if (!available) return ["/proposal-evidence-status.json"];
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  const urls = new Set(["/proposal-evidence-status.json", "/proposal-evidence.json"]);
  for (const artifact of Array.isArray(manifest.artifacts) ? manifest.artifacts : []) {
    const href = toPublicHref(artifact?.relative_path, artifact?.sha256);
    if (!href) continue;
    materializeEvidenceArtifact(artifact, href);
    const path = resolve(out, href.slice(1));
    if (path.startsWith(`${out}${sep}`) && existsSync(path) && statSync(path).isFile()) urls.add(href);
  }
  return [...urls].sort();
}

function copyCanonicalProposalEvidence() {
  const publicCopy = resolve(out, "proposal-evidence.json");
  if (existsSync(publicCopy)) return;
  const canonical = resolve(
    process.cwd(),
    "..",
    "..",
    "docs",
    "submission",
    "2026-geohackathon",
    "evidence",
    "proposal-evidence.json",
  );
  if (existsSync(canonical)) copyFileSync(canonical, publicCopy);
}

function toPublicHref(value, sha256) {
  if (typeof value !== "string") return null;
  const normalized = value.replaceAll("\\", "/").replace(/^\.\//, "");
  if (normalized.includes("..") || /^[A-Za-z]:\//.test(normalized) || normalized.startsWith("//")) return null;
  if (normalized.startsWith("apps/web/public/")) return `/${normalized.slice("apps/web/public/".length)}`;
  if (normalized.startsWith("public/")) return `/${normalized.slice("public/".length)}`;
  if (normalized.startsWith("services/geoai-runner/evidence/") && /^[a-f0-9]{64}$/i.test(sha256 ?? "")) {
    const fileName = normalized.split("/").at(-1);
    if (fileName && /^[A-Za-z0-9._-]+$/.test(fileName)) {
      return `/proposal-evidence-assets/${sha256.slice(0, 12).toLowerCase()}-${fileName}`;
    }
  }
  if (normalized.startsWith("/")) return normalized;
  return null;
}

function materializeEvidenceArtifact(artifact, href) {
  const relativePath = typeof artifact?.relative_path === "string"
    ? artifact.relative_path.replaceAll("\\", "/")
    : "";
  if (!relativePath.startsWith("services/geoai-runner/evidence/")) return;
  const isPublicImage = typeof artifact.media_type === "string" && artifact.media_type.startsWith("image/");
  const isProofReceipt = artifact.kind === "geoai_proof_receipt" && artifact.media_type === "application/json";
  if (!isPublicImage && !isProofReceipt) return;
  const repositoryRoot = resolve(process.cwd(), "..", "..");
  const allowedRoot = resolve(repositoryRoot, "services", "geoai-runner", "evidence");
  const source = resolve(repositoryRoot, relativePath);
  if (!source.startsWith(`${allowedRoot}${sep}`) || !existsSync(source) || !statSync(source).isFile()) return;
  const actualSha256 = createHash("sha256").update(readFileSync(source)).digest("hex");
  if (actualSha256 !== String(artifact.sha256).toLowerCase()) {
    throw new Error(`Proposal evidence checksum mismatch for ${relativePath}`);
  }
  const destination = resolve(out, href.slice(1));
  if (!destination.startsWith(`${out}${sep}`)) throw new Error("Proposal evidence destination escaped the static build.");
  mkdirSync(dirname(destination), { recursive: true });
  copyFileSync(source, destination);
}
