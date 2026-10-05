import assert from "node:assert/strict";
import { createHash, webcrypto } from "node:crypto";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { runInNewContext } from "node:vm";

const workerSource = readFileSync(new URL("../public/sw.js", import.meta.url), "utf8");
const illustrationUrl = "/landing/floodguard-v1/plates/w0-768.webp";
const hash = (body) => createHash("sha256").update(body).digest("hex");

/** The study-area list a build would write: `areas` maps an area id to its files (`{ url: body }`). */
function evidenceAreaList(areas) {
  const listedBy = new Map();
  for (const files of Object.values(areas)) for (const url of Object.keys(files)) listedBy.set(url, (listedBy.get(url) ?? 0) + 1);
  return Object.entries(areas).map(([aoiId, files]) => {
    const assets = Object.entries(files).map(([url, body]) => ({ url, sha256: hash(body), bytes: Buffer.byteLength(body), ...(listedBy.get(url) > 1 ? { shared: true } : {}) }));
    return { aoi_id: aoiId, bytes: assets.reduce((sum, asset) => sum + asset.bytes, 0), assets };
  });
}

function workerHarness({ version = "000000000001", profile = "competition", illustration = "approved image", illustrationUrls = [illustrationUrl], shared, caseReplay = {}, caseReplayExports = {}, evidenceAreas = {} } = {}) {
  const evidenceBodies = Object.assign({}, ...Object.values(evidenceAreas));
  const state = shared ?? { stores: new Map(), deployed: profile, requests: [], illustration, responseGate: null, replayBodies: { ...caseReplay, ...caseReplayExports, ...evidenceBodies }, fetchModes: {}, offline: false };
  const listeners = new Map();
  const messages = [];
  const pathname = (request) => new URL(typeof request === "string" ? request : request.url, "https://floodguard.test").pathname;
  const fetcher = async (request, init) => {
    if (init?.cache && typeof request === "string") request = { url: request, cache: init.cache };
    const path = pathname(request);
    state.requests.push(path);
    // Without a connection every fetch rejects, as a browser's does.
    if (state.offline) throw new TypeError("Failed to fetch");
    if (path === "/deployment-profile.json") return Response.json({ profile: state.deployed });
    if (path === "/offline-assets.json") return Response.json(["/_next/static/app.js"]);
    if (state.replayBodies && Object.hasOwn(state.replayBodies, path)) {
      // A test can hold these files back, to look at the worker while a save is running.
      if (state.fileGate) await state.fileGate;
      state.fetchModes[path] = typeof request === "string" ? undefined : request.cache;
      return new Response(state.replayBodies[path]);
    }
    if (illustrationUrls.includes(path)) {
      if (state.responseGate) await state.responseGate;
      return new Response(state.illustration, { headers: { "Content-Type": "image/webp" } });
    }
    return new Response("saved application");
  };
  const caches = {
    keys: async () => [...state.stores.keys()],
    delete: async (key) => state.stores.delete(key),
    open: async (key) => {
      if (!state.stores.has(key)) state.stores.set(key, new Map());
      const store = state.stores.get(key);
      return {
        match: async (request) => store.get(pathname(request))?.clone(),
        put: async (request, response) => { store.set(pathname(request), response.clone()); },
        delete: async (request) => store.delete(pathname(request)),
        keys: async () => [...store.keys()].map((path) => new Request(`https://floodguard.test${path}`)),
        addAll: async (requests) => {
          for (const request of requests) {
            const response = await fetcher(request);
            if (!response.ok) throw new Error("Unable to cache core application");
            store.set(pathname(request), response);
          }
        },
      };
    },
    match: async (request, options) => state.stores.get(options.cacheName)?.get(pathname(request))?.clone(),
  };
  const source = workerSource
    .replaceAll("__BUILD__", version)
    .replaceAll("__APP_PROFILE__", profile)
    .replaceAll("__CACHE_CREATED_AT__", "2026-09-15T00:00:00.000Z")
    .replace("const CORE_ASSETS = []; /* __PROFILE_CORE_ASSETS__ */", 'const CORE_ASSETS = ["/", "/deployment-profile.json"];')
    .replace("const OPTIONAL_CASE_REPLAY = []; /* __OPTIONAL_CASE_REPLAY__ */", `const OPTIONAL_CASE_REPLAY = ${JSON.stringify(profile === "competition" ? Object.entries(caseReplay).map(([url, body]) => ({ url, sha256: hash(body) })) : [])};`)
    .replace("const OPTIONAL_CASE_REPLAY_EXPORTS = []; /* __OPTIONAL_CASE_REPLAY_EXPORTS__ */", `const OPTIONAL_CASE_REPLAY_EXPORTS = ${JSON.stringify(profile === "competition" ? Object.entries(caseReplayExports).map(([url, body]) => ({ url, sha256: hash(body) })) : [])};`)
    .replace("const OPTIONAL_EVIDENCE_AREAS = []; /* __OPTIONAL_EVIDENCE_AREAS__ */", `const OPTIONAL_EVIDENCE_AREAS = ${JSON.stringify(profile === "competition" ? evidenceAreaList(evidenceAreas) : [])};`)
    .replace("const OPTIONAL_LANDING_ARTWORK = []; /* __OPTIONAL_LANDING_ARTWORK__ */", `const OPTIONAL_LANDING_ARTWORK = ${JSON.stringify(profile === "competition" ? illustrationUrls.map((url) => ({ url, sha256: hash(illustration) })) : [])};`);
  runInNewContext(source, {
    self: {
      location: { origin: "https://floodguard.test" },
      addEventListener: (type, listener) => listeners.set(type, listener),
      skipWaiting: async () => undefined,
      clients: { claim: async () => undefined, matchAll: async () => [] },
    },
    caches, fetch: fetcher, crypto: webcrypto, URL, Uint8Array, Response,
  });
  return {
    state,
    messages,
    cacheName: `floodguard-offline-${version}`,
    async dispatch(type, data) {
      const pending = [];
      listeners.get(type)({ data, waitUntil: (promise) => pending.push(promise), source: { postMessage: (message) => messages.push(message) } });
      await Promise.all(pending);
    },
    /** What the worker answers a page that requests `path`; null when the worker leaves the request alone. */
    async request(path) {
      let answer = null;
      listeners.get("fetch")({ request: { url: `https://floodguard.test${path}`, method: "GET", mode: "cors" }, respondWith: (response) => { answer = response; } });
      return answer;
    },
  };
}

test("core installation defers artwork until the post-paint request and caches it once", async () => {
  const worker = workerHarness();
  await worker.dispatch("install");
  assert.ok(worker.state.stores.get(worker.cacheName).has("/"));
  assert.ok(!worker.state.requests.includes(illustrationUrl));
  await worker.dispatch("message", { type: "FLOODGUARD_CACHE_LANDING_ARTWORK" });
  assert.equal(await worker.state.stores.get(worker.cacheName).get(illustrationUrl).clone().text(), "approved image");
  await worker.dispatch("message", { type: "FLOODGUARD_CACHE_LANDING_ARTWORK" });
  assert.equal(worker.state.requests.filter((url) => url === illustrationUrl).length, 1);
  assert.equal(worker.messages.at(-1).cached, 1);
});

test("a mismatched artwork response fails optionally without invalidating the app", async () => {
  const worker = workerHarness();
  await worker.dispatch("install");
  worker.state.illustration = "different deployment image";
  await worker.dispatch("message", { type: "FLOODGUARD_CACHE_LANDING_ARTWORK" });
  const cache = worker.state.stores.get(worker.cacheName);
  assert.ok(cache.has("/"));
  assert.ok(!cache.has(illustrationUrl));
  assert.equal(worker.messages.at(-1).failed, 1);
});

test("one optional request caches both fallback artwork and new camera frames after core installation", async () => {
  const urls = [illustrationUrl, "/landing/floodguard-v2/camera/approach-00.webp", "/landing/floodguard-v2/plates/w2.webp"];
  const worker = workerHarness({ illustrationUrls: urls });
  await worker.dispatch("install");
  assert.ok(urls.every((url) => !worker.state.requests.includes(url)));
  await worker.dispatch("message", { type: "FLOODGUARD_CACHE_LANDING_ARTWORK" });
  const cache = worker.state.stores.get(worker.cacheName);
  assert.ok(cache.has("/"));
  assert.ok(urls.every((url) => cache.has(url)));
  assert.equal(worker.messages.at(-1).total, urls.length);
  assert.equal(worker.messages.at(-1).cached, urls.length);
  assert.equal(worker.messages.at(-1).failed, 0);
});

test("an activated new build removes old art and accepts only its new artwork hash", async () => {
  const first = workerHarness();
  await first.dispatch("install");
  await first.dispatch("message", { type: "FLOODGUARD_CACHE_LANDING_ARTWORK" });
  first.state.illustration = "revised approved image";
  const second = workerHarness({ shared: first.state, version: "000000000002", illustration: "revised approved image" });
  await second.dispatch("install");
  await second.dispatch("activate");
  assert.ok(!second.state.stores.has(first.cacheName));
  await second.dispatch("message", { type: "FLOODGUARD_CACHE_LANDING_ARTWORK" });
  assert.equal(await second.state.stores.get(second.cacheName).get(illustrationUrl).text(), "revised approved image");
});

test("a public downgrade excludes artwork and cannot revive a late competition cache", { timeout: 2000 }, async () => {
  const competition = workerHarness();
  await competition.dispatch("install");
  let releaseResponse;
  competition.state.responseGate = new Promise((resolve) => { releaseResponse = resolve; });
  const pendingArtwork = competition.dispatch("message", { type: "FLOODGUARD_CACHE_LANDING_ARTWORK" });
  while (!competition.state.requests.includes(illustrationUrl)) await new Promise((resolve) => setTimeout(resolve, 0));
  competition.state.deployed = "public-production";
  const publicWorker = workerHarness({ shared: competition.state, version: "000000000003", profile: "public-production" });
  await publicWorker.dispatch("install");
  await publicWorker.dispatch("activate");
  releaseResponse();
  await pendingArtwork;
  await publicWorker.dispatch("message", { type: "FLOODGUARD_CACHE_LANDING_ARTWORK" });
  assert.deepEqual([...competition.state.stores.keys()], [publicWorker.cacheName]);
  assert.ok(!competition.state.stores.get(publicWorker.cacheName).has(illustrationUrl));
});

test("the case replay is saved only when the replay asks, hash-checked and never during installation", async () => {
  const replay = { "/studies/case/r9/timeline.json": "manifest", "/studies/case/r9/hand-codes.png": "raster" };
  const worker = workerHarness({ caseReplay: replay });
  await worker.dispatch("install");
  assert.ok(Object.keys(replay).every((url) => !worker.state.requests.includes(url)));
  worker.state.replayBodies["/studies/case/r9/hand-codes.png"] = "raster from another build";
  await worker.dispatch("message", { type: "FLOODGUARD_CACHE_CASE_REPLAY" });
  assert.deepEqual({ ...worker.messages.at(-1) }, { type: "FLOODGUARD_CASE_REPLAY_STATUS", cached: 1, failed: 1, total: 2, exports_cached: 0, exports_failed: 0, exports_total: 0 });
  const cache = worker.state.stores.get(worker.cacheName);
  assert.ok(cache.has("/studies/case/r9/timeline.json"));
  assert.ok(!cache.has("/studies/case/r9/hand-codes.png"));
  assert.equal(worker.state.fetchModes["/studies/case/r9/timeline.json"], "no-cache");
  worker.state.replayBodies["/studies/case/r9/hand-codes.png"] = "raster";
  await worker.dispatch("message", { type: "FLOODGUARD_CACHE_CASE_REPLAY" });
  assert.deepEqual({ ...worker.messages.at(-1) }, { type: "FLOODGUARD_CASE_REPLAY_STATUS", cached: 2, failed: 0, total: 2, exports_cached: 0, exports_failed: 0, exports_total: 0 });
  assert.equal(worker.state.requests.filter((url) => url === "/studies/case/r9/timeline.json").length, 1);
  assert.ok(!worker.state.requests.includes(illustrationUrl), "The replay request does not pull landing artwork.");

  const publicWorker = workerHarness({ profile: "public-production", caseReplay: replay });
  await publicWorker.dispatch("install");
  await publicWorker.dispatch("message", { type: "FLOODGUARD_CACHE_CASE_REPLAY" });
  assert.equal(publicWorker.messages.length, 0);
  assert.ok(Object.keys(replay).every((url) => !publicWorker.state.requests.includes(url)));
});

test("the replay's export pack is saved with the replay, counted apart from its data and hash-checked", async () => {
  const replay = { "/studies/case/r9/timeline.json": "manifest", "/studies/case/r9/hand-codes.png": "raster" };
  const pack = { "/studies/case/r9/exports/modelled_road_inundation_by_hour.csv": "roads", "/studies/case/r9/exports/README_licences.txt": "readme" };
  const worker = workerHarness({ caseReplay: replay, caseReplayExports: pack });
  await worker.dispatch("install");
  // Neither list is part of the blocking installation.
  assert.ok([...Object.keys(replay), ...Object.keys(pack)].every((url) => !worker.state.requests.includes(url)));
  worker.state.replayBodies["/studies/case/r9/exports/README_licences.txt"] = "readme from another build";
  await worker.dispatch("message", { type: "FLOODGUARD_CACHE_CASE_REPLAY" });
  // A download file that fails its hash is counted under exports_*: the replay's own count stays complete.
  assert.deepEqual({ ...worker.messages.at(-1) }, { type: "FLOODGUARD_CASE_REPLAY_STATUS", cached: 2, failed: 0, total: 2, exports_cached: 1, exports_failed: 1, exports_total: 2 });
  const cache = worker.state.stores.get(worker.cacheName);
  assert.ok(cache.has("/studies/case/r9/exports/modelled_road_inundation_by_hour.csv"));
  assert.ok(!cache.has("/studies/case/r9/exports/README_licences.txt"));
  worker.state.replayBodies["/studies/case/r9/exports/README_licences.txt"] = "readme";
  await worker.dispatch("message", { type: "FLOODGUARD_CACHE_CASE_REPLAY" });
  assert.deepEqual({ ...worker.messages.at(-1) }, { type: "FLOODGUARD_CASE_REPLAY_STATUS", cached: 2, failed: 0, total: 2, exports_cached: 2, exports_failed: 0, exports_total: 2 });
  // The replay data is saved first, the pack after it.
  const order = worker.state.requests.filter((url) => url.startsWith("/studies/case/r9/"));
  assert.ok(order.indexOf("/studies/case/r9/hand-codes.png") < order.indexOf("/studies/case/r9/exports/modelled_road_inundation_by_hour.csv"));
  assert.equal(worker.state.fetchModes["/studies/case/r9/exports/modelled_road_inundation_by_hour.csv"], "no-cache");

  const publicWorker = workerHarness({ profile: "public-production", caseReplay: replay, caseReplayExports: pack });
  await publicWorker.dispatch("install");
  await publicWorker.dispatch("message", { type: "FLOODGUARD_CACHE_CASE_REPLAY" });
  assert.equal(publicWorker.messages.length, 0);
  assert.ok(Object.keys(pack).every((url) => !publicWorker.state.requests.includes(url)));
});

test("a saved replay opened without a connection reports what is saved, not zero", async () => {
  const replay = { "/studies/case/r9/timeline.json": "manifest", "/studies/case/r9/hand-codes.png": "raster" };
  const pack = { "/studies/case/r9/exports/modelled_road_inundation_by_hour.csv": "roads", "/studies/case/r9/exports/README_licences.txt": "readme" };
  const complete = { type: "FLOODGUARD_CASE_REPLAY_STATUS", cached: 2, failed: 0, total: 2, exports_cached: 2, exports_failed: 0, exports_total: 2 };
  const worker = workerHarness({ caseReplay: replay, caseReplayExports: pack });
  await worker.dispatch("install");
  await worker.dispatch("message", { type: "FLOODGUARD_CACHE_CASE_REPLAY" });
  assert.deepEqual({ ...worker.messages.at(-1) }, complete);
  // The page asks again on every load. Offline, the profile check rejects: the answer is still the saved count.
  worker.state.offline = true;
  const before = worker.state.requests.length;
  await worker.dispatch("message", { type: "FLOODGUARD_CACHE_CASE_REPLAY" });
  assert.deepEqual({ ...worker.messages.at(-1) }, complete);
  assert.equal(worker.messages.at(-1).exports_cached, worker.messages.at(-1).exports_total);
  // Nothing but the profile check was tried, and the cache was not changed.
  assert.deepEqual([...new Set(worker.state.requests.slice(before))], ["/deployment-profile.json"]);
  const cache = worker.state.stores.get(worker.cacheName);
  assert.ok([...Object.keys(replay), ...Object.keys(pack)].every((url) => cache.has(url)));

  // A replay that was only partly saved says so offline, with the true count and no failure invented.
  const partial = workerHarness({ caseReplay: replay, caseReplayExports: pack });
  await partial.dispatch("install");
  partial.state.replayBodies["/studies/case/r9/exports/README_licences.txt"] = "readme from another build";
  await partial.dispatch("message", { type: "FLOODGUARD_CACHE_CASE_REPLAY" });
  partial.state.offline = true;
  await partial.dispatch("message", { type: "FLOODGUARD_CACHE_CASE_REPLAY" });
  assert.deepEqual({ ...partial.messages.at(-1) }, { ...complete, exports_cached: 1 });

  // Never saved (the replay was not opened online): zero of each, and nothing is fetched or stored offline.
  const fresh = workerHarness({ caseReplay: replay, caseReplayExports: pack });
  await fresh.dispatch("install");
  fresh.state.offline = true;
  await fresh.dispatch("message", { type: "FLOODGUARD_CACHE_CASE_REPLAY" });
  assert.deepEqual({ ...fresh.messages.at(-1) }, { ...complete, cached: 0, exports_cached: 0 });
  assert.ok(Object.keys(replay).every((url) => !fresh.state.stores.get(fresh.cacheName).has(url)));

  // The landing artwork answers the same way.
  const artwork = workerHarness();
  await artwork.dispatch("install");
  await artwork.dispatch("message", { type: "FLOODGUARD_CACHE_LANDING_ARTWORK" });
  artwork.state.offline = true;
  await artwork.dispatch("message", { type: "FLOODGUARD_CACHE_LANDING_ARTWORK" });
  assert.deepEqual({ ...artwork.messages.at(-1) }, { type: "FLOODGUARD_LANDING_ARTWORK_STATUS", cached: 1, failed: 0, total: 1 });
});

const AREA_CACHE = "floodguard-saved-areas-v1";
const report = "/library/report.html";
const coreArea = { "/library/packages/core.json": "core package", "/library/terrain/core.png": "core terrain", [report]: "shared report" };
const basinArea = { "/library/packages/basin-2024.json": "basin 2024", "/library/packages/basin-2025.json": "basin 2025", "/library/terrain/basin.png": "basin terrain", [report]: "shared report" };
const studyAreas = { core: coreArea, basin: basinArea };
const areaStatus = (aoiId, state, cached, total, bytes, failed = 0) => ({ aoi_id: aoiId, state, cached, failed, total, bytes });
const areaBytes = (files) => Object.values(files).reduce((sum, body) => sum + Buffer.byteLength(body), 0);
const plain = (value) => JSON.parse(JSON.stringify(value));

test("a study area is saved only when a page asks, hash-checked, in a cache of its own", async () => {
  const worker = workerHarness({ evidenceAreas: studyAreas });
  await worker.dispatch("install");
  await worker.dispatch("activate");
  // Nothing of the library's study areas is part of the blocking installation.
  assert.ok(Object.keys({ ...coreArea, ...basinArea }).every((url) => !worker.state.requests.includes(url)));
  await worker.dispatch("message", { type: "FLOODGUARD_EVIDENCE_AREAS_STATUS_REQUEST" });
  assert.deepEqual(plain(worker.messages.at(-1)), { type: "FLOODGUARD_EVIDENCE_AREAS_STATUS", areas: [areaStatus("core", "none", 0, 3, areaBytes(coreArea)), areaStatus("basin", "none", 0, 4, areaBytes(basinArea))], working: [] });
  // Asking for the state fetches nothing and creates no cache.
  assert.ok(!worker.state.stores.has(AREA_CACHE));
  assert.ok(Object.keys(coreArea).every((url) => !worker.state.requests.includes(url)));

  // One file arrives changed: it is refused, counted, and the area is not called saved.
  worker.state.replayBodies["/library/terrain/core.png"] = "terrain from another build";
  await worker.dispatch("message", { type: "FLOODGUARD_SAVE_EVIDENCE_AREA", aoi_id: "core" });
  assert.deepEqual(plain(worker.messages.at(-1)), { type: "FLOODGUARD_EVIDENCE_AREA_STATUS", ...areaStatus("core", "partial", 2, 3, areaBytes(coreArea), 1) });
  const saved = worker.state.stores.get(AREA_CACHE);
  assert.ok(saved.has("/library/packages/core.json") && saved.has(report) && !saved.has("/library/terrain/core.png"));
  // Each saved file carries the hash it was checked against.
  assert.equal(saved.get("/library/packages/core.json").headers.get("X-FloodGuard-SHA256"), hash("core package"));
  assert.equal(worker.state.fetchModes["/library/packages/core.json"], "no-cache");
  // The build cache holds none of it, and the other area was not touched.
  assert.ok(Object.keys(coreArea).every((url) => !worker.state.stores.get(worker.cacheName).has(url)));
  assert.ok(!worker.state.requests.includes("/library/packages/basin-2024.json"));

  // Asked again with the right bytes, only the missing file is fetched.
  worker.state.replayBodies["/library/terrain/core.png"] = "core terrain";
  await worker.dispatch("message", { type: "FLOODGUARD_SAVE_EVIDENCE_AREA", aoi_id: "core" });
  assert.deepEqual(plain(worker.messages.at(-1)), { type: "FLOODGUARD_EVIDENCE_AREA_STATUS", ...areaStatus("core", "saved", 3, 3, areaBytes(coreArea)) });
  assert.equal(worker.state.requests.filter((url) => url === "/library/packages/core.json").length, 1);
  // The report alone does not make the other area saved.
  await worker.dispatch("message", { type: "FLOODGUARD_EVIDENCE_AREAS_STATUS_REQUEST" });
  assert.deepEqual(plain(worker.messages.at(-1).areas[1]), areaStatus("basin", "none", 1, 4, areaBytes(basinArea)));
  // An area this build does not list is never saved.
  await worker.dispatch("message", { type: "FLOODGUARD_SAVE_EVIDENCE_AREA", aoi_id: "elsewhere" });
  assert.deepEqual(plain(worker.messages.at(-1)), { type: "FLOODGUARD_EVIDENCE_AREA_STATUS", ...areaStatus("elsewhere", "none", 0, 0, 0) });
});

test("the worker says which study areas it is still working on, so a page can tell a slow save from a stopped one", async () => {
  const worker = workerHarness({ evidenceAreas: studyAreas });
  await worker.dispatch("install");
  await worker.dispatch("activate");
  let release;
  worker.state.fileGate = new Promise((resolve) => { release = resolve; });
  const saving = worker.dispatch("message", { type: "FLOODGUARD_SAVE_EVIDENCE_AREA", aoi_id: "core" });
  // While the first file is still on its way, the status names the area as in work and answers at once.
  await worker.dispatch("message", { type: "FLOODGUARD_EVIDENCE_AREAS_STATUS_REQUEST" });
  assert.deepEqual(plain(worker.messages.at(-1).working), ["core"]);
  assert.equal(worker.messages.at(-1).areas[0].state, "none");
  // Nothing has passed its check yet, so no cache exists yet.
  assert.ok(!worker.state.stores.has(AREA_CACHE));

  // The browser stops the worker: the next message starts it again, with nothing in work. The page that was
  // waiting for "core" finds it gone from the list and no answer of its own.
  const restarted = workerHarness({ shared: worker.state, evidenceAreas: studyAreas });
  await restarted.dispatch("message", { type: "FLOODGUARD_EVIDENCE_AREAS_STATUS_REQUEST" });
  assert.deepEqual(plain(restarted.messages.at(-1).working), []);
  assert.equal(restarted.messages.at(-1).areas[0].state, "none");

  // A worker that was not stopped finishes, answers, and no longer lists the area.
  worker.state.fileGate = null;
  release();
  await saving;
  assert.deepEqual(plain(worker.messages.at(-1)), { type: "FLOODGUARD_EVIDENCE_AREA_STATUS", ...areaStatus("core", "saved", 3, 3, areaBytes(coreArea)) });
  await worker.dispatch("message", { type: "FLOODGUARD_EVIDENCE_AREAS_STATUS_REQUEST" });
  assert.deepEqual(plain(worker.messages.at(-1).working), []);
});

test("a save that stores nothing leaves no cache behind", async () => {
  const worker = workerHarness({ evidenceAreas: studyAreas });
  await worker.dispatch("install");
  await worker.dispatch("activate");
  // Every file arrives changed: each is refused, and the save ends with nothing stored.
  for (const url of Object.keys(coreArea)) worker.state.replayBodies[url] = `${coreArea[url]}, from another build`;
  await worker.dispatch("message", { type: "FLOODGUARD_SAVE_EVIDENCE_AREA", aoi_id: "core" });
  assert.deepEqual(plain(worker.messages.at(-1)), { type: "FLOODGUARD_EVIDENCE_AREA_STATUS", ...areaStatus("core", "none", 0, 3, areaBytes(coreArea), 3) });
  assert.ok(!worker.state.stores.has(AREA_CACHE));

  // A cache a stopped worker left empty is dropped by the next status request; one that holds a file is kept.
  worker.state.stores.set(AREA_CACHE, new Map());
  await worker.dispatch("message", { type: "FLOODGUARD_EVIDENCE_AREAS_STATUS_REQUEST" });
  assert.ok(!worker.state.stores.has(AREA_CACHE));
  for (const url of Object.keys(coreArea)) worker.state.replayBodies[url] = coreArea[url];
  await worker.dispatch("message", { type: "FLOODGUARD_SAVE_EVIDENCE_AREA", aoi_id: "core" });
  await worker.dispatch("message", { type: "FLOODGUARD_EVIDENCE_AREAS_STATUS_REQUEST" });
  assert.deepEqual([...worker.state.stores.get(AREA_CACHE).keys()].sort(), Object.keys(coreArea).sort());
});

test("a saved study area survives a new deployment when its files did not change", async () => {
  const first = workerHarness({ evidenceAreas: studyAreas });
  await first.dispatch("install");
  await first.dispatch("activate");
  await first.dispatch("message", { type: "FLOODGUARD_SAVE_EVIDENCE_AREA", aoi_id: "core" });
  await first.dispatch("message", { type: "FLOODGUARD_SAVE_EVIDENCE_AREA", aoi_id: "basin" });
  assert.equal(first.messages.at(-1).state, "saved");

  // The next deployment changes one package of the basin and nothing of the core area.
  const changedBasin = { ...basinArea, "/library/packages/basin-2025.json": "basin 2025, corrected" };
  first.state.replayBodies["/library/packages/basin-2025.json"] = "basin 2025, corrected";
  const second = workerHarness({ shared: first.state, version: "000000000002", evidenceAreas: { core: coreArea, basin: changedBasin } });
  const before = second.state.requests.length;
  await second.dispatch("install");
  await second.dispatch("activate");
  // The build cache was replaced; the saved areas were not downloaded again.
  assert.ok(!second.state.stores.has(first.cacheName));
  assert.ok(second.state.requests.slice(before).every((url) => !url.startsWith("/library/")));
  await second.dispatch("message", { type: "FLOODGUARD_EVIDENCE_AREAS_STATUS_REQUEST" });
  assert.deepEqual(plain(second.messages.at(-1).areas), [
    areaStatus("core", "saved", 3, 3, areaBytes(coreArea)),
    // Only the changed file was dropped: the area no longer reads as saved.
    areaStatus("basin", "partial", 3, 4, areaBytes(changedBasin)),
  ]);
  assert.ok(!second.state.stores.get(AREA_CACHE).has("/library/packages/basin-2025.json"));
  // Saving it again fetches the changed file only.
  await second.dispatch("message", { type: "FLOODGUARD_SAVE_EVIDENCE_AREA", aoi_id: "basin" });
  assert.deepEqual(plain(second.messages.at(-1)), { type: "FLOODGUARD_EVIDENCE_AREA_STATUS", ...areaStatus("basin", "saved", 4, 4, areaBytes(changedBasin)) });
  assert.deepEqual(second.state.requests.slice(before).filter((url) => url.startsWith("/library/")), ["/library/packages/basin-2025.json"]);

  // A deployment that no longer lists an area removes its saved files; the shared report stays for the other area.
  const third = workerHarness({ shared: first.state, version: "000000000003", evidenceAreas: { core: coreArea } });
  await third.dispatch("install");
  await third.dispatch("activate");
  assert.deepEqual([...third.state.stores.get(AREA_CACHE).keys()].sort(), Object.keys(coreArea).sort());
});

test("a saved study area can be removed; the report stays while another saved area needs it", async () => {
  const worker = workerHarness({ evidenceAreas: studyAreas });
  await worker.dispatch("install");
  await worker.dispatch("activate");
  await worker.dispatch("message", { type: "FLOODGUARD_SAVE_EVIDENCE_AREA", aoi_id: "core" });
  await worker.dispatch("message", { type: "FLOODGUARD_SAVE_EVIDENCE_AREA", aoi_id: "basin" });
  await worker.dispatch("message", { type: "FLOODGUARD_REMOVE_EVIDENCE_AREA", aoi_id: "core" });
  // The shared report does not make the removed area partly saved.
  assert.deepEqual(plain(worker.messages.at(-1)), { type: "FLOODGUARD_EVIDENCE_AREA_STATUS", ...areaStatus("core", "none", 1, 3, areaBytes(coreArea)) });
  assert.deepEqual([...worker.state.stores.get(AREA_CACHE).keys()].sort(), Object.keys(basinArea).sort());
  await worker.dispatch("message", { type: "FLOODGUARD_EVIDENCE_AREAS_STATUS_REQUEST" });
  assert.equal(worker.messages.at(-1).areas[1].state, "saved");
  // Removing the last saved area removes the cache.
  await worker.dispatch("message", { type: "FLOODGUARD_REMOVE_EVIDENCE_AREA", aoi_id: "basin" });
  assert.deepEqual(plain(worker.messages.at(-1)), { type: "FLOODGUARD_EVIDENCE_AREA_STATUS", ...areaStatus("basin", "none", 0, 4, areaBytes(basinArea)) });
  assert.ok(!worker.state.stores.has(AREA_CACHE));
  // The build cache is untouched.
  assert.ok(worker.state.stores.get(worker.cacheName).has("/"));
});

test("without a connection a saved area answers from its copy and an unsaved one is not invented", async () => {
  const worker = workerHarness({ evidenceAreas: studyAreas });
  await worker.dispatch("install");
  await worker.dispatch("activate");
  await worker.dispatch("message", { type: "FLOODGUARD_SAVE_EVIDENCE_AREA", aoi_id: "core" });
  // Online the network answers first.
  assert.equal(await (await worker.request("/library/packages/core.json")).text(), "core package");

  worker.state.offline = true;
  const offlineCopy = await worker.request("/library/packages/core.json");
  assert.equal(await offlineCopy.text(), "core package");
  // The copy is the one this build lists: the page's own SHA-256 check passes on it.
  assert.equal(hash("core package"), offlineCopy.headers.get("X-FloodGuard-SHA256"));
  assert.equal(await (await worker.request(report)).text(), "shared report");
  // An area that was not saved gets a network error, never another area's file.
  const missing = await worker.request("/library/packages/basin-2024.json");
  assert.equal(missing.type, "error");
  assert.equal(missing.ok, false);

  // The state is still reported, and a save request offline changes nothing and fetches nothing but the profile.
  const before = worker.state.requests.length;
  await worker.dispatch("message", { type: "FLOODGUARD_EVIDENCE_AREAS_STATUS_REQUEST" });
  assert.deepEqual(plain(worker.messages.at(-1).areas.map((area) => area.state)), ["saved", "none"]);
  await worker.dispatch("message", { type: "FLOODGUARD_SAVE_EVIDENCE_AREA", aoi_id: "basin" });
  assert.deepEqual(plain(worker.messages.at(-1)), { type: "FLOODGUARD_EVIDENCE_AREA_STATUS", ...areaStatus("basin", "none", 1, 4, areaBytes(basinArea)) });
  assert.deepEqual([...new Set(worker.state.requests.slice(before))], ["/deployment-profile.json"]);

  // A saved copy whose hash this build does not list is not served.
  const stale = workerHarness({ shared: worker.state, version: "000000000002", evidenceAreas: { core: { ...coreArea, "/library/packages/core.json": "core package, corrected" } } });
  assert.equal((await stale.request("/library/packages/core.json")).type, "error");
});

test("a public downgrade removes saved study areas, and the public worker saves none", async () => {
  const competition = workerHarness({ evidenceAreas: studyAreas });
  await competition.dispatch("install");
  await competition.dispatch("activate");
  await competition.dispatch("message", { type: "FLOODGUARD_SAVE_EVIDENCE_AREA", aoi_id: "core" });
  assert.ok(competition.state.stores.has(AREA_CACHE));

  // The profile changes under a competition worker that is still active: a save request then keeps nothing, and
  // the areas saved before go too.
  competition.state.deployed = "public-production";
  await competition.dispatch("message", { type: "FLOODGUARD_SAVE_EVIDENCE_AREA", aoi_id: "basin" });
  assert.deepEqual(plain(competition.messages.at(-1)), { type: "FLOODGUARD_EVIDENCE_AREA_STATUS", ...areaStatus("basin", "none", 0, 0, 0) });
  assert.ok(!competition.state.stores.has(AREA_CACHE));
  assert.ok(!competition.state.requests.includes("/library/packages/basin-2024.json"));

  // The public worker itself removes saved areas when it takes over, and answers no study-area request.
  const again = workerHarness({ evidenceAreas: studyAreas });
  await again.dispatch("install");
  await again.dispatch("activate");
  await again.dispatch("message", { type: "FLOODGUARD_SAVE_EVIDENCE_AREA", aoi_id: "core" });
  again.state.deployed = "public-production";
  const publicWorker = workerHarness({ shared: again.state, version: "000000000003", profile: "public-production", evidenceAreas: studyAreas });
  await publicWorker.dispatch("install");
  await publicWorker.dispatch("activate");
  assert.deepEqual([...again.state.stores.keys()], [publicWorker.cacheName]);
  const before = publicWorker.messages.length;
  for (const type of ["FLOODGUARD_EVIDENCE_AREAS_STATUS_REQUEST", "FLOODGUARD_SAVE_EVIDENCE_AREA", "FLOODGUARD_REMOVE_EVIDENCE_AREA"]) {
    await publicWorker.dispatch("message", { type, aoi_id: "core" });
  }
  assert.equal(publicWorker.messages.length, before);
  assert.ok(!again.state.stores.has(AREA_CACHE));
  // The public worker lists no study-area file, so it leaves such a request to its ordinary rules.
  assert.ok(Object.keys(coreArea).every((url) => !publicWorker.state.requests.slice(-3).includes(url)));
});
