import assert from "node:assert/strict";
import { createHash, webcrypto } from "node:crypto";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { runInNewContext } from "node:vm";

const workerSource = readFileSync(new URL("../public/sw.js", import.meta.url), "utf8");
const illustrationUrl = "/landing/floodguard-v1/plates/w0-768.webp";
const hash = (body) => createHash("sha256").update(body).digest("hex");

function workerHarness({ version = "000000000001", profile = "competition", illustration = "approved image", illustrationUrls = [illustrationUrl], shared, caseReplay = {} } = {}) {
  const state = shared ?? { stores: new Map(), deployed: profile, requests: [], illustration, responseGate: null, replayBodies: { ...caseReplay }, fetchModes: {} };
  const listeners = new Map();
  const messages = [];
  const pathname = (request) => new URL(typeof request === "string" ? request : request.url, "https://floodguard.test").pathname;
  const fetcher = async (request, init) => {
    if (init?.cache && typeof request === "string") request = { url: request, cache: init.cache };
    const path = pathname(request);
    state.requests.push(path);
    if (path === "/deployment-profile.json") return Response.json({ profile: state.deployed });
    if (path === "/offline-assets.json") return Response.json(["/_next/static/app.js"]);
    if (state.replayBodies && Object.hasOwn(state.replayBodies, path)) {
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
    .replace("const OPTIONAL_LANDING_ARTWORK = []; /* __OPTIONAL_LANDING_ARTWORK__ */", `const OPTIONAL_LANDING_ARTWORK = ${JSON.stringify(profile === "competition" ? illustrationUrls.map((url) => ({ url, sha256: hash(illustration) })) : [])};`);
  runInNewContext(source, {
    self: {
      location: { origin: "https://floodguard.test" },
      addEventListener: (type, listener) => listeners.set(type, listener),
      skipWaiting: async () => undefined,
      clients: { claim: async () => undefined, matchAll: async () => [] },
    },
    caches, fetch: fetcher, crypto: webcrypto, URL, Uint8Array,
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
  assert.deepEqual({ ...worker.messages.at(-1) }, { type: "FLOODGUARD_CASE_REPLAY_STATUS", cached: 1, failed: 1, total: 2 });
  const cache = worker.state.stores.get(worker.cacheName);
  assert.ok(cache.has("/studies/case/r9/timeline.json"));
  assert.ok(!cache.has("/studies/case/r9/hand-codes.png"));
  assert.equal(worker.state.fetchModes["/studies/case/r9/timeline.json"], "no-cache");
  worker.state.replayBodies["/studies/case/r9/hand-codes.png"] = "raster";
  await worker.dispatch("message", { type: "FLOODGUARD_CACHE_CASE_REPLAY" });
  assert.deepEqual({ ...worker.messages.at(-1) }, { type: "FLOODGUARD_CASE_REPLAY_STATUS", cached: 2, failed: 0, total: 2 });
  assert.equal(worker.state.requests.filter((url) => url === "/studies/case/r9/timeline.json").length, 1);
  assert.ok(!worker.state.requests.includes(illustrationUrl), "The replay request does not pull landing artwork.");

  const publicWorker = workerHarness({ profile: "public-production", caseReplay: replay });
  await publicWorker.dispatch("install");
  await publicWorker.dispatch("message", { type: "FLOODGUARD_CACHE_CASE_REPLAY" });
  assert.equal(publicWorker.messages.length, 0);
  assert.ok(Object.keys(replay).every((url) => !publicWorker.state.requests.includes(url)));
});
