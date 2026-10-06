import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { closeSync, ftruncateSync, mkdtempSync, mkdirSync, openSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve, sep } from "node:path";
import { test } from "node:test";
import { gzipSync } from "node:zlib";
import { assertPublicEvidenceText, auditEvidenceLibrary, collectEvidenceLibraryAssets, EVIDENCE_CATALOG_ASSET, readWorkerEvidenceAreas } from "./evidence-library-assets.mjs";

function fixture(run, mutate = () => {}, mutateCatalog = () => {}) {
  const out = mkdtempSync(resolve(tmpdir(), "floodguard-evidence-assets-test-"));
  const root = resolve(out, "evidence-library");
  mkdirSync(root);
  const data = { id: "test", package_version: "v1", aoi_id: "test-aoi", event_id: "test-event", dataset_mode: "candidate", official_warning: false, operational_status: "non_operational", assessment: { fpps: null, action_class: null }, layers: [], report_url: "/evidence-library/report.md" };
  const catalog = { non_operational: true, package_version: "v1", datasets: [{ id: "test-source", rights: { public_derivatives: false } }], packages: [{ id: "test", aoi_id: "test-aoi", event_id: "test-event", url: "/evidence-library/package.json" }] };
  try {
    mutate(data, catalog);
    mutateCatalog(catalog);
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

test("groups the files a reader saves on request by study area and keeps download archives out of them", () => {
  const archive = gzipSync(JSON.stringify({ schema_version: "synthetic-test", edges: [] }));
  const png = Buffer.from("synthetic terrain preview");
  fixture((out, root) => {
    // A second study area that shares the report with the first.
    const second = { id: "second", package_version: "v1", aoi_id: "second-aoi", event_id: "test-event", dataset_mode: "candidate", official_warning: false, operational_status: "non_operational", assessment: { fpps: null, action_class: null }, layers: [], report_url: "/evidence-library/report.md" };
    const secondBytes = JSON.stringify(second);
    writeFileSync(resolve(root, "second.json"), secondBytes);
    writeFileSync(resolve(root, "database.json.gz"), archive);
    writeFileSync(resolve(root, "terrain.png"), png);
    const catalog = JSON.parse(readFileSync(resolve(root, "catalog.json"), "utf8"));
    catalog.packages.push({ id: "second", aoi_id: "second-aoi", event_id: "test-event", url: "/evidence-library/second.json", sha256: createHash("sha256").update(secondBytes).digest("hex") });
    writeFileSync(resolve(root, "catalog.json"), JSON.stringify(catalog));

    const library = auditEvidenceLibrary(out);
    const digest = (bytes) => createHash("sha256").update(bytes).digest("hex");
    const reportRecord = { url: "/evidence-library/report.md", sha256: digest("Synthetic test report"), bytes: 21, shared: true };
    assert.deepEqual(library.areas.map((area) => area.aoi_id), ["test-aoi", "second-aoi"]);
    assert.deepEqual(library.areas[0].assets, [
      // The package is pinned by the catalogue's own SHA-256; the report and the preview are hashed at build time.
      { url: "/evidence-library/package.json", sha256: catalog.packages[0].sha256, bytes: readFileSync(resolve(root, "package.json")).byteLength },
      reportRecord,
      { url: "/evidence-library/terrain.png", sha256: digest(png), bytes: png.byteLength },
    ]);
    assert.deepEqual(library.areas[1].assets, [{ url: "/evidence-library/second.json", sha256: catalog.packages[1].sha256, bytes: Buffer.byteLength(secondBytes) }, reportRecord]);
    assert.equal(library.areas[0].bytes, library.areas[0].assets.reduce((sum, asset) => sum + asset.bytes, 0));
    // The download archive is published and hash-checked, and belongs to no study area's saved copy.
    assert.deepEqual(library.onlineOnly, [{ url: "/evidence-library/database.json.gz", sha256: digest(archive), bytes: archive.byteLength }]);
    assert.ok(library.areas.every((area) => area.assets.every((asset) => asset.url !== "/evidence-library/database.json.gz")));
    // The catalogue is the one file left for the blocking installation, and it is in no study area.
    assert.equal(EVIDENCE_CATALOG_ASSET, "/evidence-library/catalog.json");
    assert.ok(library.areas.every((area) => area.assets.every((asset) => asset.url !== EVIDENCE_CATALOG_ASSET)));
    assert.deepEqual(library.urls, collectEvidenceLibraryAssets(out));
    assert.equal(library.urls.length, 6);

    // The worker's list is read back as written.
    const worker = `const OPTIONAL_EVIDENCE_AREAS = ${JSON.stringify(library.areas)};\nconst CORE_ASSETS = [];`;
    assert.deepEqual(readWorkerEvidenceAreas(worker), library.areas);
    assert.throws(() => readWorkerEvidenceAreas("const CORE_ASSETS = [];"), /no study-area list/);
  }, (data) => {
    data.downloads = [{ title: "Synthetic database", url: "/evidence-library/database.json.gz", sha256: createHash("sha256").update(archive).digest("hex") }];
    data.layers = [{ id: "terrain", dataset_id: "cleared-source", availability: "available", image_url: "/evidence-library/terrain.png" }];
  }, (catalog) => { catalog.datasets.push({ id: "cleared-source", rights: { public_derivatives: true } }); });
});
