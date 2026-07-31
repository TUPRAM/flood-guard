const CACHE_NAME = "floodguard-offline-__BUILD__";
const APP_PROFILE = "__APP_PROFILE__";
const CACHE_CREATED_AT = "__CACHE_CREATED_AT__";
const CORE_ASSETS = []; /* __PROFILE_CORE_ASSETS__ */

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
  if (event.data?.type === "FLOODGUARD_STATUS_REQUEST") {
    const message = { type: "FLOODGUARD_STATUS", cache_name: CACHE_NAME, profile: APP_PROFILE, cached_at: CACHE_CREATED_AT };
    if (event.ports?.[0]) event.ports[0].postMessage(message);
    else event.source?.postMessage(message);
  }
});

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
