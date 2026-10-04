import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { relative, resolve, sep } from "node:path";
import { assertPublicEvidenceText } from "./evidence-library-assets.mjs";

/** Check every bilingual download against its candidate Public projection. */
export function collectCaseBriefAssets(out) {
  const root = resolve(out, "briefs");
  const catalogPath = resolve(root, "catalog.json");
  if (!existsSync(catalogPath)) throw new Error("Case brief catalog is missing.");
  const catalog = JSON.parse(readFileSync(catalogPath, "utf8"));
  const sourceCatalogBytes = readFileSync(resolve(out, "public-case-projections", "catalog.json"));
  const sourceCatalog = JSON.parse(sourceCatalogBytes.toString("utf8"));
  const evidenceCatalogBytes = readFileSync(resolve(out, "evidence-library", "catalog.json"));
  assertPublicEvidenceText(catalog);
  if (catalog.schema_version !== "floodguard.case_briefs.v1"
    || catalog.source_projection_catalog_sha256 !== sha256(sourceCatalogBytes)
    || catalog.source_evidence_catalog_sha256 !== sha256(evidenceCatalogBytes)
    || catalog.package_version !== sourceCatalog.package_version
    || !Array.isArray(catalog.briefs) || catalog.briefs.length !== sourceCatalog.packages.length) {
    throw new Error("Case brief catalog or source binding is invalid.");
  }
  const urls = new Set(["/briefs/catalog.json"]);
  const seen = new Set();
  for (const brief of catalog.briefs) {
    const source = sourceCatalog.packages.find((item) => item.id === brief.id);
    if (!source || seen.has(brief.id) || !/^[A-Za-z0-9_-]+$/.test(brief.id)
      || brief.aoi_id !== source.aoi_id || brief.event_id !== source.event_id
      || brief.source_projection_sha256 !== source.sha256
      || brief.source_package_sha256 !== source.source_package_sha256) {
      throw new Error(`Case brief identity differs from source projection: ${brief.id}`);
    }
    seen.add(brief.id);
    for (const [kind, extension] of [["html", "html"], ["pdf", "pdf"]]) {
      const url = `/briefs/${brief.id}.${extension}`;
      if (brief[`${kind}_url`] !== url || !/^[a-f0-9]{64}$/.test(brief[`${kind}_sha256`] ?? "")) {
        throw new Error(`Case brief ${kind} path or hash is invalid: ${brief.id}`);
      }
      const path = resolve(out, url.slice(1));
      if (!path.startsWith(`${root}${sep}`) || !existsSync(path) || !statSync(path).isFile()) {
        throw new Error(`Case brief asset is missing: ${url}`);
      }
      const bytes = readFileSync(path);
      if (sha256(bytes) !== brief[`${kind}_sha256`]) throw new Error(`Case brief hash mismatch: ${url}`);
      if (kind === "html") {
        const content = bytes.toString("utf8");
        assertPublicEvidenceText(content);
        if (!content.includes('data-dataset-mode="candidate"')
          || !content.includes('data-official-warning="false"')
          || !content.includes('data-accepted-fpps="unavailable"')
          || !content.includes(brief.source_projection_sha256)
          || /<script\b|\son[a-z]+\s*=/i.test(content)) {
          throw new Error(`Case brief HTML is unsafe or lacks candidate status: ${url}`);
        }
      } else if (bytes.subarray(0, 5).toString("ascii") !== "%PDF-") {
        throw new Error(`Case brief is not a PDF: ${url}`);
      }
      urls.add(url);
    }
  }
  for (const file of walk(root)) {
    const url = `/${relative(out, file).split(sep).join("/")}`;
    if (!urls.has(url)) throw new Error(`Unlisted case brief asset would be published: ${url}`);
  }
  return [...urls].sort();
}

function sha256(bytes) { return createHash("sha256").update(bytes).digest("hex"); }
function walk(directory) {
  return readdirSync(directory).flatMap((name) => {
    const path = resolve(directory, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}
