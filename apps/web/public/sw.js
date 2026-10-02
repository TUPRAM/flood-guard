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
let artworkTask = null;
let caseReplayTask = null;

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
 */
async function cacheOptionalAssets(assets, fetchCache) {
  const result = { cached: 0, failed: 0, total: assets.length };
  try {
    if (!(await caches.keys()).includes(CACHE_NAME) || !(await competitionStillDeployed())) return result;
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

async function competitionStillDeployed() {
  const response = await fetch("/deployment-profile.json", { cache: "no-store" });
  return response.ok && (await response.json()).profile === "competition";
}

self.addEventListener("fetch", (event) => {
  const requestUrl = new URL(event.request.url);
  if (event.request.method !== "GET" || requestUrl.origin !== self.location.origin || requestUrl.pathname.startsWith("/api/")) {
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
