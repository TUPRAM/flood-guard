import { createHash } from "node:crypto";
import { readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { relative, resolve, sep } from "node:path";

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
];
const buildHash = createHash("sha256");
for (const path of versionedFiles) {
  buildHash.update(relative(out, path).split(sep).join("/"));
  buildHash.update(readFileSync(path));
}
const cacheVersion = buildHash.digest("hex").slice(0, 12);
const serviceWorkerPath = resolve(out, "sw.js");
const serviceWorker = readFileSync(serviceWorkerPath, "utf8");
if (!serviceWorker.includes("__BUILD__")) {
  throw new Error("Service-worker build token is missing.");
}
writeFileSync(serviceWorkerPath, serviceWorker.replaceAll("__BUILD__", cacheVersion), "utf8");

console.log(`offline asset manifest: ${assets.length} production chunks; cache ${cacheVersion}`);
