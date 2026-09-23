import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { closeSync, ftruncateSync, mkdtempSync, mkdirSync, openSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve, sep } from "node:path";
import { test } from "node:test";
import { gzipSync } from "node:zlib";
import { assertPublicEvidenceText, collectEvidenceLibraryAssets } from "./evidence-library-assets.mjs";

function fixture(run, mutate = () => {}) {
  const out = mkdtempSync(resolve(tmpdir(), "floodguard-evidence-assets-test-"));
  const root = resolve(out, "evidence-library");
  mkdirSync(root);
  const data = { id: "test", package_version: "v1", aoi_id: "test-aoi", event_id: "test-event", dataset_mode: "candidate", official_warning: false, operational_status: "non_operational", assessment: { fpps: null, action_class: null }, layers: [], report_url: "/evidence-library/report.md" };
  const catalog = { non_operational: true, package_version: "v1", datasets: [{ id: "test-source", rights: { public_derivatives: false } }], packages: [{ id: "test", aoi_id: "test-aoi", event_id: "test-event", url: "/evidence-library/package.json" }] };
  try {
    mutate(data, catalog);
    const bytes = JSON.stringify(data);
    catalog.packages[0].sha256 = createHash("sha256").update(bytes).digest("hex");
    writeFileSync(resolve(root, "package.json"), bytes);
    writeFileSync(resolve(root, "catalog.json"), JSON.stringify(catalog));
    writeFileSync(resolve(root, "report.md"), "Synthetic test report");
    run(out, root);
  } finally {
    if (!resolve(out).startsWith(`${resolve(tmpdir())}${sep}floodguard-evidence-assets-test-`)) throw new Error("Unsafe test cleanup target");
    rmSync(out, { recursive: true, force: true });
  }
}

test("includes only bound package and report assets", () => fixture((out) => {
  assert.deepEqual(collectEvidenceLibraryAssets(out), ["/evidence-library/catalog.json", "/evidence-library/package.json", "/evidence-library/report.md"]);
}));
test("rejects a package changed after catalog hashing", () => fixture((out, root) => {
  writeFileSync(resolve(root, "package.json"), "{}");
  assert.throws(() => collectEvidenceLibraryAssets(out), /hash mismatch/);
}));
test("rejects an accidentally copied unlisted raw file", () => fixture((out, root) => {
  writeFileSync(resolve(root, "private-station-observations.csv"), "not cleared");
  assert.throws(() => collectEvidenceLibraryAssets(out), /Unlisted evidence asset/);
}));
test("rejects a report outside the static evidence namespace", () => fixture((out) => {
  assert.throws(() => collectEvidenceLibraryAssets(out), /Invalid evidence-library URL/);
}, (data) => { data.report_url = "https://unapproved.example/report.md"; }));
test("rejects geometry from a source lacking derivative clearance", () => fixture((out) => {
  assert.throws(() => collectEvidenceLibraryAssets(out), /Uncleared evidence derivative/);
}, (data) => { data.layers = [{ id: "restricted", dataset_id: "test-source", availability: "available", data: { type: "FeatureCollection", features: [] } }]; }));
test("rejects complete primary scoring in candidate packages", () => fixture((out) => {
  assert.throws(() => collectEvidenceLibraryAssets(out), /Invalid evidence package boundary/);
}, (data) => { data.assessment.fpps = 85; data.assessment.action_class = "A"; }));
test("rejects private or raw source fields in JSON and escaped report appendices", () => {
  for (const key of ["coordinator_name", "contact:phone", "เบอร์โทรศัพท์", "ชื่อผู้ประสานงาน", "raw_observations", "absolute_file_path"]) {
    assert.throws(() => assertPublicEvidenceText({ nested: { [key]: "private fixture" } }), /Private\/raw field/);
    assert.throws(() => assertPublicEvidenceText(`<pre>{&quot;${key}&quot;: &quot;private fixture&quot;}</pre>`), /Private\/raw field/);
  }
  assert.doesNotThrow(() => assertPublicEvidenceText({ name: "Public test facility", source_inventory_sha256: "a".repeat(64) }));
});
test("rejects filesystem paths embedded in metadata", () => {
  for (const path of ["C:\\Users\\private\\raw.csv", "file:///tmp/source.csv", "/home/user/private.csv", "\\\\private-server\\share\\data.csv"]) {
    assert.throws(() => assertPublicEvidenceText({ summary: path }), /filesystem path/);
  }
});
test("decodes bounded HTML entities before checking reports for private keys and paths", () => {
  for (const value of [
    "&#x43;:&#x5c;Users&#x5c;iputu&#x5c;private.csv",
    "C&colon;&bsol;Users&bsol;private&bsol;raw.csv",
    "&amp;#x43;:&#92;Users&#92;private.csv",
    "&#x43:&#x5cUsers&#x5ciputu&#x5cprivate.csv",
  ]) assert.throws(() => assertPublicEvidenceText(value), /filesystem path|Numeric HTML entity/);
  for (const value of [
    "{&#x22;api_key&#x22;:&#x22;secret&#x22;}",
    "{&quot;api&lowbar;key&quot;:&quot;secret&quot;}",
    "{&#34api_key&#34:&#34secret&#34}",
    "{&quotapi_key&quot:&quotsecret&quot}",
  ]) assert.throws(() => assertPublicEvidenceText(value), /Private\/raw field|Numeric HTML entity/);
  assert.throws(() => assertPublicEvidenceText(`&${"amp;".repeat(9)}#x43;`), /Nested HTML entity/);
});
test("binds and inspects the gzip derivative database download", () => {
  const archive = gzipSync(JSON.stringify({ schema_version: "synthetic-test", edges: [], source_name: "Synthetic fixture" }));
  fixture((out, root) => {
    writeFileSync(resolve(root, "database.json.gz"), archive);
    assert.ok(collectEvidenceLibraryAssets(out).includes("/evidence-library/database.json.gz"));
    writeFileSync(resolve(root, "database.json.gz"), Buffer.from("corrupted archive"));
    assert.throws(() => collectEvidenceLibraryAssets(out), /download hash mismatch/);
  }, (data) => { data.downloads = [{ title: "Synthetic database", url: "/evidence-library/database.json.gz", sha256: createHash("sha256").update(archive).digest("hex") }]; });
});
test("rejects private fields inside an otherwise correctly hashed gzip archive", () => {
  const archive = gzipSync(JSON.stringify({ sites: [{ "โทรศัพท์": "PRIVATE_TEST" }] }));
  fixture((out, root) => {
    writeFileSync(resolve(root, "database.json.gz"), archive);
    assert.throws(() => collectEvidenceLibraryAssets(out), /Private\/raw field/);
  }, (data) => { data.downloads = [{ title: "Synthetic database", url: "/evidence-library/database.json.gz", sha256: createHash("sha256").update(archive).digest("hex") }]; });
});
test("rejects a correctly hashed file that is not valid gzip and an unlisted gzip", () => {
  const archive = Buffer.from("not gzip");
  fixture((out, root) => {
    writeFileSync(resolve(root, "database.json.gz"), archive);
    assert.throws(() => collectEvidenceLibraryAssets(out), /header|gzip|compression/i);
  }, (data) => { data.downloads = [{ title: "Synthetic database", url: "/evidence-library/database.json.gz", sha256: createHash("sha256").update(archive).digest("hex") }]; });
  fixture((out, root) => {
    writeFileSync(resolve(root, "unlisted.json.gz"), gzipSync("{}"));
    assert.throws(() => collectEvidenceLibraryAssets(out), /Unlisted evidence asset/);
  });
});
test("rejects an oversized compressed download before reading or auditing it", () => fixture((out, root) => {
  const path = resolve(root, "database.json.gz");
  const handle = openSync(path, "w");
  try { ftruncateSync(handle, 80 * 1024 * 1024 + 1); } finally { closeSync(handle); }
  assert.throws(() => collectEvidenceLibraryAssets(out), /exceeds 80 MiB/);
}, (data) => { data.downloads = [{ title: "Oversized fixture", url: "/evidence-library/database.json.gz", sha256: "0".repeat(64) }]; }));
