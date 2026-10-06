const CACHE_NAME = "floodguard-offline-__BUILD__";
const APP_PROFILE = "__APP_PROFILE__";
const CACHE_CREATED_AT = "__CACHE_CREATED_AT__";
const CORE_ASSETS = []; /* __PROFILE_CORE_ASSETS__ */
const OPTIONAL_LANDING_ARTWORK = []; /* __OPTIONAL_LANDING_ARTWORK__ */
// Opt-in bucket: the Mae Sai case replay's manifest and the files it lists (derived from the manifest at
// build time). Saved only when the replay page asks after rendering online, never during installation.
const OPTIONAL_CASE_REPLAY = []; /* __OPTIONAL_CASE_REPLAY__ */
// The replay's export pack: tables and one map layer to download, listed apart from the replay data and counted
// against a budget of their own. Saved after the replay data, on the same request, so a download link on a
// saved replay still answers without a connection.
const OPTIONAL_CASE_REPLAY_EXPORTS = []; /* __OPTIONAL_CASE_REPLAY_EXPORTS__ */
// Opt-in buckets, one for each study area of the evidence library (derived from the library's catalogue at build
// time): the area's package file or files, its terrain preview and the report they share, each pinned by SHA-256.
// Saved only when a page asks (a reader opens the area while connected, or presses its save button), never during
// installation, and kept in a cache of their own so that a new deployment keeps every saved file whose hash did not
// change. The database archives a package offers for download are never kept here.
const OPTIONAL_EVIDENCE_AREAS = []; /* __OPTIONAL_EVIDENCE_AREAS__ */
const EVIDENCE_AREA_CACHE = "floodguard-saved-areas-v1";
// Each saved file carries the hash it was checked against, so a later build can tell an unchanged file from a stale one.
const EVIDENCE_HASH_HEADER = "X-FloodGuard-SHA256";
const EVIDENCE_AREA_FILES = new Map(OPTIONAL_EVIDENCE_AREAS.flatMap((area) => area.assets.map((asset) => [asset.url, asset.sha256])));
let artworkTask = null;
let caseReplayTask = null;
// Saving and removing study areas run one after another: areas share a file (the report).
let evidenceAreaQueue = Promise.resolve();
// Study areas with a save or a removal queued or running in this run of the worker. A page that waits for one asks
// for the status meanwhile; an area it no longer finds here, with no answer received, was interrupted (the browser
// stopped the worker, and this list started empty again).
const evidenceAreaWork = new Map();

self.addEventListener("install", (event) => {
  event.waitUntil(
    Promise.all([
      fetch("/offline-assets.json", { cache: "no-store" }).then((response) => {
        if (!response.ok) throw new Error("Offline asset manifest is unavailable");
        return response.json();
      }),
      fetch("/deployment-profile.json", { cache: "no-store" }).then((response) => {
        if (!response.ok) throw new Error("Deployment profile is unavailable");
        return response.json();
      }),
    ]).then(([generatedAssets, deploymentProfile]) => {
      if (deploymentProfile.profile !== APP_PROFILE) {
        throw new Error(`Deployment profile changed during install: expected ${APP_PROFILE}`);
      }
      return caches.open(CACHE_NAME)
        .then((cache) => cache.addAll([...CORE_ASSETS, ...generatedAssets]))
        .then(() => fetch("/deployment-profile.json", { cache: "no-store" }))
        .then((response) => {
          if (!response.ok) throw new Error("Deployment profile is unavailable after caching");
          return response.json();
        })
        .then((finalProfile) => {
          if (finalProfile.profile !== APP_PROFILE) {
            throw new Error(`Deployment profile changed while caching: expected ${APP_PROFILE}`);
          }
        });
    })
      .then(() => APP_PROFILE === "public-production" ? self.skipWaiting() : undefined)
      .catch(async (error) => {
        await caches.delete(CACHE_NAME);
        throw error;
      })
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME && /^floodguard-offline-/.test(key)).map((key) => caches.delete(key))))
      // Saved study areas outlive the build cache: keep the files this build still lists, drop the rest.
      .then(() => reconcileSavedEvidence().catch(() => undefined))
      .then(() => self.clients.claim())
      .then(() => self.clients.matchAll({ type: "window" }))
      .then((clients) => {
        const message = { type: "FLOODGUARD_CACHE_READY", cache_name: CACHE_NAME, profile: APP_PROFILE, cached_at: CACHE_CREATED_AT };
        for (const client of clients) client.postMessage(message);
      })
  );
});

self.addEventListener("message", (event) => {
  if (event.data?.type === "SKIP_WAITING") self.skipWaiting();
  if (event.data?.type === "FLOODGUARD_CACHE_LANDING_ARTWORK" && APP_PROFILE === "competition") {
    artworkTask ??= cacheLandingArtwork().finally(() => { artworkTask = null; });
    event.waitUntil(artworkTask.then((result) => {
      const message = { type: "FLOODGUARD_LANDING_ARTWORK_STATUS", ...result };
      if (event.ports?.[0]) event.ports[0].postMessage(message);
      else event.source?.postMessage(message);
    }));
  }
  if (event.data?.type === "FLOODGUARD_CACHE_CASE_REPLAY" && APP_PROFILE === "competition") {
    caseReplayTask ??= cacheCaseReplay().finally(() => { caseReplayTask = null; });
    event.waitUntil(caseReplayTask.then((result) => {
      const message = { type: "FLOODGUARD_CASE_REPLAY_STATUS", ...result };
      if (event.ports?.[0]) event.ports[0].postMessage(message);
      else event.source?.postMessage(message);
    }));
  }
  if (event.data?.type === "FLOODGUARD_EVIDENCE_AREAS_STATUS_REQUEST" && APP_PROFILE === "competition") {
    // With nothing in work, a cache left empty by an interrupted save is dropped first (in the queue, so it cannot
    // run beside a save). `working` names the areas this run of the worker is still saving or removing.
    const tidy = evidenceAreaWork.size === 0 ? queueEvidenceAreaTask(dropEmptyEvidenceCache).catch(() => undefined) : Promise.resolve();
    event.waitUntil(tidy.then(evidenceAreasStatus).then((areas) => reply(event, { type: "FLOODGUARD_EVIDENCE_AREAS_STATUS", areas, working: [...evidenceAreaWork.keys()] })));
  }
  if (event.data?.type === "FLOODGUARD_SAVE_EVIDENCE_AREA" && APP_PROFILE === "competition") {
    const aoiId = String(event.data.aoi_id ?? "");
    event.waitUntil(trackEvidenceAreaWork(aoiId, () => saveEvidenceArea(aoiId)).then((result) => reply(event, { type: "FLOODGUARD_EVIDENCE_AREA_STATUS", ...result })));
  }
  if (event.data?.type === "FLOODGUARD_REMOVE_EVIDENCE_AREA" && APP_PROFILE === "competition") {
    const aoiId = String(event.data.aoi_id ?? "");
    event.waitUntil(trackEvidenceAreaWork(aoiId, () => removeEvidenceArea(aoiId)).then((result) => reply(event, { type: "FLOODGUARD_EVIDENCE_AREA_STATUS", ...result })));
  }
  if (event.data?.type === "FLOODGUARD_STATUS_REQUEST") {
    const message = { type: "FLOODGUARD_STATUS", cache_name: CACHE_NAME, profile: APP_PROFILE, cached_at: CACHE_CREATED_AT };
    if (event.ports?.[0]) event.ports[0].postMessage(message);
    else event.source?.postMessage(message);
  }
});

function cacheLandingArtwork() {
  return cacheOptionalAssets(OPTIONAL_LANDING_ARTWORK, "no-store");
}

/**
 * Save the case replay's data, then its export pack. The replay's own counts (cached, failed, total) describe the
 * data the page needs; the export pack is reported apart (exports_*), so a failed download file never makes the
 * replay look incomplete.
 */
async function cacheCaseReplay() {
  // "no-cache" revalidates against the network, so files the page has just loaded are not downloaded twice.
  const result = await cacheOptionalAssets(OPTIONAL_CASE_REPLAY, "no-cache");
  const pack = await cacheOptionalAssets(OPTIONAL_CASE_REPLAY_EXPORTS, "no-cache");
  return { ...result, exports_cached: pack.cached, exports_failed: pack.failed, exports_total: pack.total };
}

/**
 * Save optional, build-pinned files ({ url, sha256 }) into the current cache. Each file is stored only when
 * its SHA-256 matches this build; failures are counted and never invalidate the saved application.
 *
 * Without a connection the deployment profile cannot be re-checked and nothing can be fetched. The request then
 * reports what this build's cache already holds and changes nothing: a fully saved replay opened offline must not
 * read as "0 of N files saved".
 */
async function cacheOptionalAssets(assets, fetchCache) {
  const result = { cached: 0, failed: 0, total: assets.length };
  try {
    if (!(await caches.keys()).includes(CACHE_NAME)) return result;
    let deployed;
    try {
      deployed = await competitionStillDeployed();
    } catch {
      result.cached = await countSavedAssets(assets);
      return result;
    }
    if (!deployed) return result;
    const cache = await caches.open(CACHE_NAME);
    for (const asset of assets) {
      if (!(await caches.keys()).includes(CACHE_NAME)) return result;
      if (await cache.match(asset.url)) { result.cached += 1; continue; }
      try {
        const response = await fetch(asset.url, { cache: fetchCache });
        if (!response.ok) throw new Error("Optional asset unavailable");
        const digest = await crypto.subtle.digest("SHA-256", await response.clone().arrayBuffer());
        const hash = [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
        if (hash !== asset.sha256) throw new Error("Optional asset belongs to a different build");
        if (!(await caches.keys()).includes(CACHE_NAME)) return result;
        await cache.put(asset.url, response);
        result.cached += 1;
      } catch { result.failed += 1; }
    }
    // A public-profile downgrade must not retain a late optional-asset task.
    if (!(await competitionStillDeployed())) await caches.delete(CACHE_NAME);
  } catch {
    // Optional downloads never invalidate the saved planning app.
  }
  return result;
}

/** How many of the listed files this build's cache already holds. Reads only: nothing is fetched or stored. */
async function countSavedAssets(assets) {
  const cache = await caches.open(CACHE_NAME);
  let saved = 0;
  for (const asset of assets) {
    if (await cache.match(asset.url)) saved += 1;
  }
  return saved;
}

function reply(event, message) {
  if (event.ports?.[0]) event.ports[0].postMessage(message);
  else event.source?.postMessage(message);
}

function queueEvidenceAreaTask(task) {
  const run = evidenceAreaQueue.then(task, task);
  evidenceAreaQueue = run.catch(() => undefined);
  return run;
}

/** Queue a save or a removal and list its area as in work until it has ended, whatever the outcome. */
function trackEvidenceAreaWork(aoiId, task) {
  evidenceAreaWork.set(aoiId, (evidenceAreaWork.get(aoiId) ?? 0) + 1);
  const done = () => {
    const left = (evidenceAreaWork.get(aoiId) ?? 1) - 1;
    if (left > 0) evidenceAreaWork.set(aoiId, left);
    else evidenceAreaWork.delete(aoiId);
  };
  return queueEvidenceAreaTask(task).then((result) => { done(); return result; }, (error) => { done(); throw error; });
}

/** A saved-areas cache that holds nothing is removed: an empty cache must not be left behind by a save. */
async function dropEmptyEvidenceCache() {
  if (!(await caches.keys()).includes(EVIDENCE_AREA_CACHE)) return;
  const cache = await caches.open(EVIDENCE_AREA_CACHE);
  if ((await cache.keys()).length === 0) await caches.delete(EVIDENCE_AREA_CACHE);
}

async function sha256Hex(buffer) {
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

/**
 * True when the saved copy of a study-area file is the one this build lists (same SHA-256). `cache` is the opened
 * saved-areas cache; without it the cache is looked up by name, which never creates it.
 */
async function savedEvidenceMatches(cache, asset) {
  const response = cache ? await cache.match(asset.url) : await caches.match(asset.url, { cacheName: EVIDENCE_AREA_CACHE });
  return Boolean(response && response.headers.get(EVIDENCE_HASH_HEADER) === asset.sha256);
}

/**
 * What is saved of one study area: "saved" when every file is, "none" when no file of its own is (the shared report
 * alone does not make an area saved), otherwise "partial".
 */
async function evidenceAreaState(area) {
  const result = { aoi_id: area.aoi_id, state: "none", cached: 0, failed: 0, total: area.assets.length, bytes: area.bytes };
  if (!(await caches.keys()).includes(EVIDENCE_AREA_CACHE)) return result;
  const cache = await caches.open(EVIDENCE_AREA_CACHE);
  let own = 0;
  for (const asset of area.assets) {
    if (!(await savedEvidenceMatches(cache, asset))) continue;
    result.cached += 1;
    if (!asset.shared) own += 1;
  }
  result.state = result.cached === result.total ? "saved" : own > 0 ? "partial" : "none";
  return result;
}

/** The saved state of every study area. Reads only: nothing is fetched or stored. */
async function evidenceAreasStatus() {
  const areas = [];
  for (const area of OPTIONAL_EVIDENCE_AREAS) areas.push(await evidenceAreaState(area));
  return areas;
}

function unknownEvidenceArea(aoiId) {
  return { aoi_id: aoiId, state: "none", cached: 0, failed: 0, total: 0, bytes: 0 };
}

/**
 * Save one study area because a page asked: a reader opened the area while connected, or pressed its save button.
 * Each file is stored only when its SHA-256 matches this build's list; a file that fails is counted and nothing else
 * is touched. Without a connection nothing can be fetched: the request then reports what is already saved, as the
 * case replay's request does. The cache is created with the first file that passes, and removed again when the save
 * ends with nothing in it.
 */
async function saveEvidenceArea(aoiId) {
  const area = OPTIONAL_EVIDENCE_AREAS.find((item) => item.aoi_id === aoiId);
  if (!area) return unknownEvidenceArea(aoiId);
  let failed = 0;
  try {
    let deployed;
    try {
      deployed = await competitionStillDeployed();
    } catch {
      return evidenceAreaState(area);
    }
    // A public-profile downgrade must not retain study areas, saved earlier or by a late request.
    if (!deployed) {
      await caches.delete(EVIDENCE_AREA_CACHE);
      return unknownEvidenceArea(aoiId);
    }
    for (const asset of area.assets) {
      if (await savedEvidenceMatches(null, asset)) continue;
      try {
        // "no-cache" revalidates against the network, so a file the page has just loaded is not downloaded twice.
        const response = await fetch(asset.url, { cache: "no-cache" });
        if (!response.ok) throw new Error("Study-area file unavailable");
        const body = await response.arrayBuffer();
        if (await sha256Hex(body) !== asset.sha256) throw new Error("Study-area file belongs to a different build");
        const cache = await caches.open(EVIDENCE_AREA_CACHE);
        await cache.put(asset.url, new Response(body, {
          status: 200,
          headers: { "Content-Type": response.headers.get("Content-Type") || "application/octet-stream", [EVIDENCE_HASH_HEADER]: asset.sha256 },
        }));
      } catch { failed += 1; }
    }
    if (!(await competitionStillDeployed())) {
      await caches.delete(EVIDENCE_AREA_CACHE);
      return unknownEvidenceArea(aoiId);
    }
  } catch {
    // A failed save never invalidates the saved application.
  }
  await dropEmptyEvidenceCache().catch(() => undefined);
  return { ...(await evidenceAreaState(area)), failed };
}

/**
 * Remove one saved study area. A shared file (the report) stays while another area that lists it still has a file
 * of its own saved.
 */
async function removeEvidenceArea(aoiId) {
  const area = OPTIONAL_EVIDENCE_AREAS.find((item) => item.aoi_id === aoiId);
  if (!area) return unknownEvidenceArea(aoiId);
  if (!(await caches.keys()).includes(EVIDENCE_AREA_CACHE)) return evidenceAreaState(area);
  const cache = await caches.open(EVIDENCE_AREA_CACHE);
  const stillNeeded = new Set();
  for (const other of OPTIONAL_EVIDENCE_AREAS) {
    if (other.aoi_id === aoiId) continue;
    let ownSaved = false;
    for (const asset of other.assets) {
      if (!asset.shared && await savedEvidenceMatches(cache, asset)) { ownSaved = true; break; }
    }
    if (ownSaved) for (const asset of other.assets) stillNeeded.add(asset.url);
  }
  for (const asset of area.assets) {
    if (!stillNeeded.has(asset.url)) await cache.delete(asset.url);
  }
  if ((await cache.keys()).length === 0) await caches.delete(EVIDENCE_AREA_CACHE);
  return evidenceAreaState(area);
}

/**
 * On activation: the public profile keeps no study area. A competition build keeps each saved file it still lists
 * with the same SHA-256 and deletes every other one, so an area whose files changed reads as not (or partly) saved.
 */
async function reconcileSavedEvidence() {
  if (!(await caches.keys()).includes(EVIDENCE_AREA_CACHE)) return;
  if (APP_PROFILE !== "competition") {
    await caches.delete(EVIDENCE_AREA_CACHE);
    return;
  }
  const cache = await caches.open(EVIDENCE_AREA_CACHE);
  for (const request of await cache.keys()) {
    const response = await cache.match(request);
    const listed = EVIDENCE_AREA_FILES.get(new URL(request.url).pathname);
    if (!listed || !response || response.headers.get(EVIDENCE_HASH_HEADER) !== listed) await cache.delete(request);
  }
  if ((await cache.keys()).length === 0) await caches.delete(EVIDENCE_AREA_CACHE);
}

/** The saved copy of a study-area file, only when it is the one this build lists; otherwise a network error. */
async function matchSavedEvidence(pathname) {
  const response = await caches.match(pathname, { cacheName: EVIDENCE_AREA_CACHE });
  return response && response.headers.get(EVIDENCE_HASH_HEADER) === EVIDENCE_AREA_FILES.get(pathname) ? response : Response.error();
}

async function competitionStillDeployed() {
  const response = await fetch("/deployment-profile.json", { cache: "no-store" });
  return response.ok && (await response.json()).profile === "competition";
}

self.addEventListener("fetch", (event) => {
  const requestUrl = new URL(event.request.url);
  if (event.request.method !== "GET" || requestUrl.origin !== self.location.origin || requestUrl.pathname.startsWith("/api/")) {
    return;
  }
  // A study-area file: the network first, then the copy the reader saved (also for its download link).
  if (EVIDENCE_AREA_FILES.has(requestUrl.pathname)) {
    event.respondWith(fetch(event.request).catch(() => matchSavedEvidence(requestUrl.pathname)));
    return;
  }
  const isMutableRequest =
    event.request.mode === "navigate" ||
    CORE_ASSETS.includes(requestUrl.pathname) ||
    requestUrl.pathname === "/offline-assets.json" ||
    requestUrl.pathname === "/sw.js";

  if (isMutableRequest) {
    event.respondWith(
      fetch(event.request)
        .catch(() => matchOfflineRequest(event.request))
    );
    return;
  }

  event.respondWith(
    matchCurrentCache(event.request).then(
      (cached) =>
        cached ||
        fetch(event.request)
    )
  );
});

async function matchCurrentCache(request) {
  return caches.match(request, { cacheName: CACHE_NAME });
}

async function matchOfflineRequest(request) {
  const direct = await caches.match(request, {
    cacheName: CACHE_NAME,
    ignoreSearch: request.mode === "navigate",
  });
  if (direct || request.mode !== "navigate") return direct;
  const requestUrl = new URL(request.url);
  const canonicalPath = requestUrl.pathname === "/" || requestUrl.pathname.endsWith("/")
    ? requestUrl.pathname
    : `${requestUrl.pathname}/`;
  return caches.match(canonicalPath, { cacheName: CACHE_NAME, ignoreSearch: true });
}
