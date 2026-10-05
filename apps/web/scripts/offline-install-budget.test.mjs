import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, resolve, sep } from "node:path";
import { test } from "node:test";

import { CASE_REPLAY_BUDGET_BYTES, CASE_REPLAY_EXPORT_BUDGET_BYTES } from "./case-replay-inventory.mjs";
import { megabytes, OFFLINE_INSTALL_BUDGET_BYTES, offlineInstallBytes, readWorkerCoreAssets, verifyOfflineInstall } from "./offline-install-budget.mjs";

function build(files, run) {
  const out = mkdtempSync(resolve(tmpdir(), "floodguard-install-budget-test-"));
  try {
    for (const [path, content] of Object.entries(files)) {
      mkdirSync(dirname(resolve(out, path)), { recursive: true });
      writeFileSync(resolve(out, path), content);
    }
    run(out);
  } finally {
    if (!resolve(out).startsWith(`${resolve(tmpdir())}${sep}floodguard-install-budget-test-`)) throw new Error("Unsafe test cleanup target");
    rmSync(out, { recursive: true, force: true });
  }
}

const site = {
  "index.html": "x".repeat(100),
  "studio/library/index.html": "x".repeat(200),
  "catalog.json": "x".repeat(50),
  "_next/static/chunks/app.js": "x".repeat(1000),
};

test("the blocking installation has a 12 MB budget, apart from the replay's own budgets", () => {
  assert.equal(OFFLINE_INSTALL_BUDGET_BYTES, 12_000_000);
  // The replay's data and its export pack are opt-in buckets with budgets of their own; they are unchanged.
  assert.equal(CASE_REPLAY_BUDGET_BYTES, 6_500_000);
  assert.equal(CASE_REPLAY_EXPORT_BUDGET_BYTES, 1_000_000);
  assert.equal(megabytes(10_466_870), "10.5");
});

test("counts every file of the blocking list once, a route as its index.html", () => build(site, (out) => {
  const install = offlineInstallBytes(out, ["/", "/studio/library/", "/catalog.json", "/"], ["/_next/static/chunks/app.js"]);
  assert.deepEqual({ files: install.files, bytes: install.bytes, core_bytes: install.core_bytes, chunk_bytes: install.chunk_bytes, budget_bytes: install.budget_bytes },
    { files: 4, bytes: 1350, core_bytes: 350, chunk_bytes: 1000, budget_bytes: 12_000_000 });
  assert.deepEqual(install.largest[0], { url: "/_next/static/chunks/app.js", bytes: 1000 });
}));

test("fails above the budget and names the largest files", () => build(site, (out) => {
  assert.equal(offlineInstallBytes(out, ["/", "/catalog.json"], ["/_next/static/chunks/app.js"], 1150).bytes, 1150);
  assert.throws(
    () => offlineInstallBytes(out, ["/", "/catalog.json"], ["/_next/static/chunks/app.js"], 1149),
    /blocking offline installation is 1150 bytes .* over its 1149-byte budget .*\/_next\/static\/chunks\/app\.js .*saves on request/s,
  );
}));

test("refuses a listed file that is missing or outside the build", () => build(site, (out) => {
  assert.throws(() => offlineInstallBytes(out, ["/missing.json"], []), /Offline install file is missing: \/missing\.json/);
  assert.throws(() => offlineInstallBytes(out, ["/../secret"], []), /Invalid offline install URL/);
  assert.throws(() => offlineInstallBytes(out, ["/studio/"], []), /Offline install file is missing: \/studio\//);
  assert.throws(() => offlineInstallBytes(out, ["https://elsewhere.example/a.js"], []), /Invalid offline install URL/);
}));

test("measures a built directory from its own service worker and chunk list", () => build({
  ...site,
  "sw.js": 'const CORE_ASSETS = ["/","/studio/library/","/catalog.json"];\nconst OPTIONAL_EVIDENCE_AREAS = [{"aoi_id":"a","bytes":900000000,"assets":[{"url":"/packages/a.json","sha256":"0","bytes":900000000}]}];',
  "offline-assets.json": '["/_next/static/chunks/app.js"]',
}, (out) => {
  // A study area's size is not part of the installation: only CORE_ASSETS and the chunk list are.
  const install = verifyOfflineInstall(out);
  assert.equal(install.bytes, 1350);
  assert.deepEqual(install.coreAssets, ["/", "/studio/library/", "/catalog.json"]);
  assert.throws(() => verifyOfflineInstall(out, 1000), /over its 1000-byte budget/);
  assert.throws(() => readWorkerCoreAssets("const APP_PROFILE = 'x';"), /no CORE_ASSETS list/);
}));

test("the build and the asset checks all apply the budget", () => {
  const scripts = resolve(import.meta.dirname);
  // The build fails before the worker is finalized; the artifact check and the offline check read the built worker.
  const builder = readFileSync(resolve(scripts, "write-offline-assets.mjs"), "utf8");
  assert.ok(builder.indexOf("offlineInstallBytes(out, coreAssets, assets)") > 0);
  assert.ok(builder.indexOf("offlineInstallBytes(out, coreAssets, assets)") < builder.indexOf("writeFileSync(\n  serviceWorkerPath"));
  for (const name of ["profile-artifact-smoke.mjs", "offline-smoke.mjs"]) {
    assert.match(readFileSync(resolve(scripts, name), "utf8"), /verifyOfflineInstall\(out\)/, `${name} must check the installation budget`);
  }
});
