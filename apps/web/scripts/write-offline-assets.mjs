import { createHash } from "node:crypto";
import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, relative, resolve, sep } from "node:path";
import { collectEvidenceLibraryAssets } from "./evidence-library-assets.mjs";

const out = resolve(process.cwd(), "out");
const nextStatic = resolve(out, "_next", "static");
const appProfile = resolveAppProfile(process.env.FLOODGUARD_APP_PROFILE ?? process.env.NEXT_PUBLIC_FLOODGUARD_APP_PROFILE);

if (appProfile === "public-production") prunePublicProductionOutput();
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
const evidenceLibraryAssets = appProfile === "competition" ? collectEvidenceLibraryAssets(out) : [];
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
      "/command/",
      "/studio/",
      "/studio/library/",
      "/studio/brief/",
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
      ...evidenceLibraryAssets,
    ];
const deploymentProfile = {
  profile: appProfile,
  entry: "/",
  included_surfaces: appProfile === "competition" ? ["public", "command", "studio"] : ["public"],
  staff_access: appProfile === "competition" ? "presentation_boundary_only" : "not_deployed",
  cache_policy: appProfile === "competition" ? "competition_open_evidence" : "public_projection_only",
};
writeFileSync(resolve(out, "deployment-profile.json"), `${JSON.stringify(deploymentProfile, null, 2)}\n`, "utf8");

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
    resolve(out, "command", "index.html"),
    resolve(out, "studio", "index.html"),
    resolve(out, "studio", "library", "index.html"),
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
  ...evidenceLibraryAssets.map((url) => resolve(out, url.slice(1))),
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
const cacheVersion = buildHash.digest("hex").slice(0, 12);
const cacheCreatedAt = new Date().toISOString();
if (!serviceWorker.includes("__BUILD__") || !serviceWorker.includes("__APP_PROFILE__") || !serviceWorker.includes("__CACHE_CREATED_AT__") || !serviceWorker.includes("__PROFILE_CORE_ASSETS__")) {
  throw new Error("Service-worker build tokens are missing.");
}
writeFileSync(
  serviceWorkerPath,
  serviceWorker
    .replaceAll("__BUILD__", cacheVersion)
    .replaceAll("__APP_PROFILE__", appProfile)
    .replaceAll("__CACHE_CREATED_AT__", cacheCreatedAt)
    .replace(
      "const CORE_ASSETS = []; /* __PROFILE_CORE_ASSETS__ */",
      `const CORE_ASSETS = ${JSON.stringify(coreAssets)};`,
    ),
  "utf8",
);

console.log(`offline asset manifest: ${assets.length} production chunks, ${optionalLandingAssets.size} optional landing chunks excluded, ${proposalEvidenceAssets.length} proposal evidence assets; profile ${appProfile}; cache ${cacheVersion}`);

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
    "command",
    "studio",
    "evidence-library",
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
