import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve, sep } from "node:path";

const root = resolve(import.meta.dirname, "../../..");
const publicRoot = resolve(root, "apps/web/public");
const prefix = "/studies/c2s-ms-20260915/r1/";
const digest = (bytes) => createHash("sha256").update(bytes).digest("hex");
function readAsset(href) {
  if (!href.startsWith("/studies/") || href.includes("..")) throw new Error(`Invalid study asset path: ${href}`);
  const path = resolve(publicRoot, href.slice(1));
  if (!path.startsWith(`${publicRoot}${sep}`)) throw new Error("Study asset escapes public root");
  return readFileSync(path);
}
function verify(href, sha256, expectedBytes) {
  const bytes = readAsset(href);
  if (digest(bytes) !== sha256 || (expectedBytes != null && bytes.length !== expectedBytes)) throw new Error(`Study asset checksum/length mismatch: ${href}`);
  return bytes;
}
const manifestBytes = readAsset(`${prefix}manifest.json`);
const pin = readFileSync(resolve(root, "apps/web/src/lib/study-report-release.ts"), "utf8").match(/"([a-f0-9]{64})"/)?.[1];
if (digest(manifestBytes) !== pin) throw new Error("Committed study manifest differs from compiled pin");
const manifest = JSON.parse(manifestBytes);
for (const asset of manifest.assets) verify(asset.href, asset.sha256, asset.bytes);
const index = JSON.parse(readAsset(`${prefix}visual-index.json`));
const pngs = new Set();
function visit(value) {
  if (Array.isArray(value)) return value.forEach(visit);
  if (!value || typeof value !== "object") return;
  if (typeof value.url === "string" && value.url.endsWith(".png")) {
    const bytes = verify(value.url, value.sha256);
    if (bytes.toString("ascii", 1, 4) !== "PNG" || bytes.readUInt32BE(16) > 256 || bytes.readUInt32BE(20) > 256) throw new Error(`Invalid preview dimensions: ${value.url}`);
    pngs.add(value.url);
  }
  Object.values(value).forEach(visit);
}
visit(index);
if (index.chips.length !== 111 || pngs.size !== 2147) throw new Error("Incomplete test-chip or preview inventory");
const historical = JSON.parse(readAsset("/studies/mae-sai-geoai/2026-07-30-r1/manifest.json"));
for (const asset of [historical.report, ...historical.assets]) verify(asset.href, asset.sha256, asset.bytes);

// Windows newline conversion must not change a hash-bound artifact on checkout.
const entries = execFileSync("git", ["ls-files", "--stage", "-z", "apps/web/public/studies"], { cwd: root, encoding: "utf8" }).split("\0").filter(Boolean);
for (const entry of entries) {
  const [info, path] = entry.split("\t");
  const [, blobId] = info.split(" ");
  const bytes = readFileSync(resolve(root, path));
  const actual = createHash("sha1").update(`blob ${bytes.length}\0`).update(bytes).digest("hex");
  if (actual !== blobId) throw new Error(`Git changes exact study bytes or has stale staged content: ${path}`);
}
console.log(`Study integrity passed: ${manifest.assets.length} C2S JSON assets, ${pngs.size} previews, ${historical.assets.length + 1} historical assets and ${entries.length} byte-identical Git blobs.`);
