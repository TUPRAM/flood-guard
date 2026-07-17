import { createHash } from "node:crypto";
import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { dirname, relative, resolve, sep } from "node:path";

const out = resolve(process.cwd(), "out");
const nextStatic = resolve(out, "_next", "static");

function walk(directory) {
  return readdirSync(directory).flatMap((name) => {
    const path = resolve(directory, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

const assets = walk(nextStatic)
  .map((path) => `/${relative(out, path).split(sep).join("/")}`)
  .sort();

writeFileSync(resolve(out, "offline-assets.json"), `${JSON.stringify(assets, null, 2)}\n`, "utf8");

copyCanonicalProposalEvidence();
const proposalEvidenceAssets = collectProposalEvidenceAssets();

const versionedFiles = [
  ...assets.map((path) => resolve(out, path.slice(1))),
  resolve(out, "index.html"),
  resolve(out, "public", "index.html"),
  resolve(out, "command", "index.html"),
  resolve(out, "studio", "index.html"),
  resolve(out, "manifest.webmanifest"),
  resolve(out, "icon.svg"),
  resolve(out, "offline-demo", "bundle.json"),
  resolve(out, "offline-demo", "areas.geojson"),
  resolve(out, "offline-demo", "roads.geojson"),
  ...proposalEvidenceAssets.map((url) => resolve(out, url.slice(1))),
];
const buildHash = createHash("sha256");
for (const path of versionedFiles) {
  buildHash.update(relative(out, path).split(sep).join("/"));
  buildHash.update(readFileSync(path));
}
const cacheVersion = buildHash.digest("hex").slice(0, 12);
const serviceWorkerPath = resolve(out, "sw.js");
const serviceWorker = readFileSync(serviceWorkerPath, "utf8");
if (!serviceWorker.includes("__BUILD__") || !serviceWorker.includes("__PROPOSAL_EVIDENCE_ASSETS__")) {
  throw new Error("Service-worker build tokens are missing.");
}
writeFileSync(
  serviceWorkerPath,
  serviceWorker
    .replaceAll("__BUILD__", cacheVersion)
    .replace(
      "const PROPOSAL_EVIDENCE_ASSETS = []; /* __PROPOSAL_EVIDENCE_ASSETS__ */",
      `const PROPOSAL_EVIDENCE_ASSETS = ${JSON.stringify(proposalEvidenceAssets)};`,
    ),
  "utf8",
);

console.log(`offline asset manifest: ${assets.length} production chunks, ${proposalEvidenceAssets.length} proposal evidence assets; cache ${cacheVersion}`);

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
